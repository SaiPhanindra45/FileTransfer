import socket
import os
import sys
import time
import argparse


def progress_bar(current, total, bar_length=50):
    progress = min(1.0, current / total)
    arrow = '=' * int(progress * bar_length)
    spaces = ' ' * (bar_length - len(arrow))
    percent = progress * 100
    sys.stdout.write(f'\r[{arrow}{spaces}] {percent:.1f}% ({current}/{total} bytes)')
    sys.stdout.flush()

def request_file(server_address, server_port, filename, save_as=None):
    if not save_as:
        save_as = os.path.basename(filename)
    
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print(f"Connecting to {server_address}:{server_port}...")
    
    try:
        client_socket.connect((server_address, server_port))
        print(f"Connected successfully. Requesting file: {filename}")
        
        client_socket.send(f"GET:{filename}".encode())
        
        response = client_socket.recv(1024).decode()
        
        if response.startswith("ERROR:"):
            print(f"Server error: {response[6:]}")
            client_socket.close()
            return False
        
        if response.startswith("SIZE:"):
            file_size = int(response[5:])
            print(f"File found, size: {file_size} bytes")
            client_socket.send(b"READY")
        else:
            print("Unexpected server response")
            client_socket.close()
            return False
        
        bytes_received = 0
        buffer_size = 8192
        start_time = time.time()
        
        with open(save_as, 'wb') as file:
            while bytes_received < file_size:
                data = client_socket.recv(buffer_size)
                if not data:
                    break
                file.write(data)
                bytes_received += len(data)
                progress_bar(bytes_received, file_size)
        
        end_time = time.time()
        duration = end_time - start_time
        transfer_rate = (file_size / 1024 / 1024) / duration if duration > 0 else 0
        
        print(f"\nFile received successfully as '{save_as}'")
        print(f"Transfer rate: {transfer_rate:.2f} MB/s ({duration:.2f} seconds)")
        
        return True
    
    except ConnectionRefusedError:
        print("Connection failed: The server is not running or the address is incorrect.")
    except socket.timeout:
        print("Connection timed out: The server took too long to respond.")
    except Exception as e:
        print(f"An error occurred: {str(e)}")
    finally:
        client_socket.close()
    
    return False

def list_files(server_address, server_port):
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    try:
        client_socket.connect((server_address, server_port))
        client_socket.send(b"LIST")
        
        response = client_socket.recv(8192).decode()
        if response.startswith("FILES:"):
            files = response[6:].split(',')
            print("\nAvailable files on server:")
            for i, file in enumerate(files, 1):
                print(f"{i}. {file}")
        else:
            print(f"Server error: {response}")
    except Exception as e:
        print(f"An error occurred: {str(e)}")
    finally:
        client_socket.close()

def main():
    parser = argparse.ArgumentParser(description='File Transfer Client')
    parser.add_argument('--server', default='localhost', help='Server address (default: localhost)')
    parser.add_argument('--port', type=int, default=12345, help='Server port (default: 12345)')
    parser.add_argument('--list', action='store_true', help='List available files')
    parser.add_argument('--file', help='File to download')
    parser.add_argument('--save-as', help='Save file with a different name')
    
    args = parser.parse_args()
    
    if args.list:
        list_files(args.server, args.port)
    elif args.file:
        request_file(args.server, args.port, args.file, args.save_as)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
