import subprocess
import time
import argparse
import matplotlib.pyplot as plt
import numpy as np
import socket
import os
import sys
import threading

def check_netem_installed():
    """Check if NetEm is available on the system"""
    try:
        result = subprocess.run(['tc', 'qdisc'], 
                               stdout=subprocess.PIPE, 
                               stderr=subprocess.PIPE)
        return result.returncode == 0
    except FileNotFoundError:
        return False

def setup_network_condition(interface, delay=None, loss=None, bandwidth=None):
    """Set up network conditions using NetEm"""
    # First remove any existing rules
    subprocess.run(['sudo', 'tc', 'qdisc', 'del', 'dev', interface, 'root'], 
                  stderr=subprocess.DEVNULL)
    
    # Build the basic command
    cmd = ['sudo', 'tc', 'qdisc', 'add', 'dev', interface, 'root', 'netem']
    
    # Add parameters
    if delay:
        cmd.extend(['delay', f'{delay}ms'])
    if loss:
        cmd.extend(['loss', f'{loss}%'])
    if bandwidth:
        # Need to add HTB qdisc with rate limiting
        subprocess.run(['sudo', 'tc', 'qdisc', 'add', 'dev', interface, 'root', 'handle', '1:', 'htb', 'default', '10'])
        subprocess.run(['sudo', 'tc', 'class', 'add', 'dev', interface, 'parent', '1:', 'classid', '1:10', 'htb', 'rate', f'{bandwidth}kbit'])
        # Then add netem for additional parameters if needed
        if delay or loss:
            return setup_network_condition(interface, delay, loss, None)
        return True
    
    # Execute the command
    result = subprocess.run(cmd)
    return result.returncode == 0

def reset_network_condition(interface):
    """Reset network conditions to normal"""
    subprocess.run(['sudo', 'tc', 'qdisc', 'del', 'dev', interface, 'root'], 
                  stderr=subprocess.DEVNULL)
    print(f"Network conditions reset for {interface}")

def transfer_file(server, port, filename, results_dict, condition_name):
    """Transfer a file and record the results"""
    start_time = time.time()
    
    # Create a client socket
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    try:
        # Connect to the server
        client_socket.connect((server, port))
        
        # Request the file
        client_socket.send(f"GET:{filename}".encode())
        
        # Get the server's response
        response = client_socket.recv(1024).decode()
        
        if response.startswith("ERROR:"):
            print(f"Server error: {response[6:]}")
            results_dict[condition_name] = {"success": False, "error": response[6:]}
            return
        
        # Get file size
        if response.startswith("SIZE:"):
            file_size = int(response[5:])
            client_socket.send(b"READY")
        else:
            print("Unexpected server response")
            results_dict[condition_name] = {"success": False, "error": "Unexpected response"}
            return
        
        # Receive the file
        bytes_received = 0
        buffer_size = 4096
        temp_filename = f"test_received_{int(time.time())}.tmp"
        
        with open(temp_filename, 'wb') as file:
            while bytes_received < file_size:
                data = client_socket.recv(buffer_size)
                if not data:
                    break
                file.write(data)
                bytes_received += len(data)
        
        end_time = time.time()
        duration = end_time - start_time
        transfer_rate = (file_size / 1024 / 1024) / duration if duration > 0 else 0
        
        # Record results
        results_dict[condition_name] = {
            "success": True,
            "size": file_size,
            "duration": duration,
            "transfer_rate": transfer_rate,
            "bytes_received": bytes_received
        }
        
        # Clean up temporary file
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
        
    except Exception as e:
        results_dict[condition_name] = {"success": False, "error": str(e)}
    finally:
        client_socket.close()

def run_performance_tests(server, port, filename, interface, test_scenarios):
    """Run performance tests with different network conditions"""
    if not check_netem_installed():
        print("Error: NetEm is not installed or requires root privileges.")
        print("Please install the 'iproute2' package and ensure you can run 'sudo'.")
        return
    
    results = {}
    
    # Test with normal network conditions first
    print("\nRunning baseline test (normal network conditions)...")
    reset_network_condition(interface)
    transfer_file(server, port, filename, results, "Baseline")
    
    # Run tests with each network condition
    for scenario in test_scenarios:
        name = scenario["name"]
        print(f"\nSetting up network condition: {name}")
        print(f"Parameters: {scenario}")
        
        if setup_network_condition(
            interface, 
            scenario.get("delay"), 
            scenario.get("loss"),
            scenario.get("bandwidth")
        ):
            print(f"Network condition set. Starting transfer test...")
            transfer_file(server, port, filename, results, name)
            time.sleep(1)  # Small delay between tests
        else:
            print(f"Failed to set network condition for {name}")
            results[name] = {"success": False, "error": "Failed to set network condition"}
    
    # Reset network conditions
    reset_network_condition(interface)
    
    # Display and plot results
    display_results(results)
    plot_results(results)

def display_results(results):
    """Display the test results in a table"""
    print("\n===== TEST RESULTS =====")
    print("Condition            | Success | Size (MB) | Duration (s) | Transfer Rate (MB/s)")
    print("-------------------- | ------- | --------- | ------------ | -------------------")
    
    for name, data in results.items():
        if data["success"]:
            size_mb = data["size"] / (1024 * 1024)
            print(f"{name:20} | {'✓':7} | {size_mb:9.2f} | {data['duration']:12.2f} | {data['transfer_rate']:19.2f}")
        else:
            print(f"{name:20} | {'✗':7} | {'N/A':9} | {'N/A':12} | {'N/A':19}")
            print(f"  Error: {data['error']}")

def plot_results(results):
    """Plot the test results as a bar chart"""
    plt.figure(figsize=(12, 6))
    
    # Extract successful tests
    successful_tests = {name: data for name, data in results.items() if data["success"]}
    
    if not successful_tests:
        print("No successful tests to plot.")
        return
    
    names = list(successful_tests.keys())
    transfer_rates = [data["transfer_rate"] for data in successful_tests.values()]
    durations = [data["duration"] for data in successful_tests.values()]
    
    x = np.arange(len(names))
    width = 0.35
    
    fig, ax1 = plt.subplots(figsize=(12, 6))
    
    # Plot transfer rates
    bars1 = ax1.bar(x - width/2, transfer_rates, width, label='Transfer Rate (MB/s)', color='blue')
    ax1.set_ylabel('Transfer Rate (MB/s)', color='blue')
    ax1.tick_params(axis='y', labelcolor='blue')
    
    # Create second y-axis for duration
    ax2 = ax1.twinx()
    bars2 = ax2.bar(x + width/2, durations, width, label='Duration (s)', color='red')
    ax2.set_ylabel('Duration (s)', color='red')
    ax2.tick_params(axis='y', labelcolor='red')
    
    # Add some text for labels, title and custom x-axis tick labels
    ax1.set_xlabel('Network Condition')
    ax1.set_title('File Transfer Performance Under Different Network Conditions')
    ax1.set_xticks(x)
    ax1.set_xticklabels(names, rotation=45, ha='right')
    
    # Add a legend
    ax1.legend(loc='upper left')
    ax2.legend(loc='upper right')
    
    fig.tight_layout()
    
    # Save the plot
    plt.savefig('network_test_results.png')
    print("\nResults plot saved as 'network_test_results.png'")
    
    # Display the plot
    plt.show()

def main():
    parser = argparse.ArgumentParser(description='Network Performance Testing Tool')
    parser.add_argument('--server', default='localhost', help='Server address (default: localhost)')
    parser.add_argument('--port', type=int, default=12345, help='Server port (default: 12345)')
    parser.add_argument('--file', required=True, help='File to transfer for testing')
    parser.add_argument('--interface', required=True, help='Network interface to apply conditions to (e.g., eth0)')
    
    args = parser.parse_args()
    
    # Define test scenarios
    test_scenarios = [
        {"name": "High Latency", "delay": 100, "loss": 0, "bandwidth": None},
        {"name": "Packet Loss", "delay": 0, "loss": 5, "bandwidth": None},
        {"name": "Limited Bandwidth", "delay": 0, "loss": 0, "bandwidth": 1000},  # 1 Mbps
        {"name": "Poor Connection", "delay": 200, "loss": 10, "bandwidth": 500},  # 500 Kbps with high latency and loss
    ]
    
    print("Network Performance Testing Tool")
    print("================================")
    print(f"Server: {args.server}:{args.port}")
    print(f"Test File: {args.file}")
    print(f"Network Interface: {args.interface}")
    
    # Check if running as root
    if os.geteuid() != 0:
        print("\nWarning: This script requires root privileges to modify network settings.")
        print("Please run with sudo or as root.")
        sys.exit(1)
    
    run_performance_tests(args.server, args.port, args.file, args.interface, test_scenarios)

if __name__ == "__main__":
    main()