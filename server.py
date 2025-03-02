import socket
import os
import threading
import argparse
import time
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("server_log.txt"),
        logging.StreamHandler()
    ]
)

class FileTransferServer:
    def __init__(self, host='0.0.0.0', port=12345, directory='.', buffer_size=8192):
        self.host = host
        self.port = port
        self.directory = directory
        self.buffer_size = buffer_size
        self.active_connections = 0
        self.server_socket = None
        self.running = False
    
    def start(self):
        """Start the file transfer server"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Allow port reuse
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(10)  # Allow up to 10 pending connections
            
            self.running = True
            logging.info(f"Server started on {self.host}:{self.port}, serving files from '{self.directory}'")
            
            while self.running:
                try:
                    client_conn, client_addr = self.server_socket.accept()
                    self.active_connections += 1
                    logging.info(f"New connection from {client_addr[0]}:{client_addr[1]} (Active: {self.active_connections})")
                    
                    # Handle each client in a separate thread
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_conn, client_addr)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                except Exception as e:
                    if self.running:  # Only log if not caused by shutdown
                        logging.error(f"Error accepting connection: {str(e)}")
        except Exception as e:
            logging.error(f"Server start error: {str(e)}")
        finally:
            self.stop()
    
    def stop(self):
        """Stop the server"""
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        logging.info("Server stopped")
    
    def handle_client(self, client_conn, client_addr):
        """Handle client connection and file requests"""
        client_ip = client_addr[0]
        try:
            client_conn.settimeout(60)  # 60 second timeout
            request = client_conn.recv(1024).decode()
            
            if request.startswith("GET:"):
                filename = request[4:]
                self.send_file(client_conn, filename, client_ip)
            elif request == "LIST":
                self.list_files(client_conn, client_ip)
            else:
                logging.warning(f"Invalid request from {client_ip}: {request}")
                client_conn.send(b"ERROR:Invalid request")
        except Exception as e:
            logging.error(f"Error handling client {client_ip}: {str(e)}")
        finally:
            try:
                client_conn.close()
            except:
                pass
            self.active_connections -= 1
            logging.info(f"Connection closed with {client_ip} (Active: {self.active_connections})")
    
    def send_file(self, client_conn, filename, client_ip):
        """Send a file to the client"""
        filepath = os.path.join(self.directory, filename)
        
        # Prevent directory traversal attacks
        normalized_path = os.path.normpath(filepath)
        if not normalized_path.startswith(os.path.normpath(self.directory)):
            logging.warning(f"Security: Client {client_ip} attempted path traversal: {filename}")
            client_conn.send(b"ERROR:Access denied")
            return
        
        try:
            if not os.path.exists(filepath):
                logging.info(f"File not found: {filepath}, requested by {client_ip}")
                client_conn.send(b"ERROR:File not found")
                return
            
            file_size = os.path.getsize(filepath)
            client_conn.send(f"SIZE:{file_size}".encode())
            
            # Wait for client to be ready
            response = client_conn.recv(1024)
            if response != b"READY":
                return
            
            # Track transfer statistics
            start_time = time.time()
            bytes_sent = 0
            
            # In server.py, ensure the file is opened in binary mode
            with open(filepath, 'rb') as file:
                while True:
                    data = file.read(self.buffer_size)
                    if not data:
                        break
                    client_conn.sendall(data)  # Use sendall to ensure all data is sent
                    bytes_sent += len(data)
            
            # Calculate statistics
            end_time = time.time()
            duration = end_time - start_time
            transfer_rate = (file_size / 1024 / 1024) / duration if duration > 0 else 0
            
            logging.info(f"File '{filename}' ({file_size} bytes) sent to {client_ip}")
            logging.info(f"Transfer rate: {transfer_rate:.2f} MB/s ({duration:.2f} seconds)")
        
        except Exception as e:
            logging.error(f"Error sending file to {client_ip}: {str(e)}")
            try:
                client_conn.send(f"ERROR:{str(e)}".encode())
            except:
                pass
    
    def list_files(self, client_conn, client_ip):
        """Send a list of available files to the client"""
        try:
            files = [f for f in os.listdir(self.directory) 
                    if os.path.isfile(os.path.join(self.directory, f))]
            
            response = "FILES:" + ",".join(files)
            client_conn.send(response.encode())
            logging.info(f"File list sent to {client_ip}")
        except Exception as e:
            logging.error(f"Error sending file list to {client_ip}: {str(e)}")
            try:
                client_conn.send(f"ERROR:{str(e)}".encode())
            except:
                pass

def main():
    parser = argparse.ArgumentParser(description='File Transfer Server')
    parser.add_argument('--host', default='0.0.0.0', help='Server address to bind to (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=12345, help='Port to listen on (default: 12345)')
    parser.add_argument('--dir', default='.', help='Directory to serve files from (default: current directory)')
    parser.add_argument('--buffer', type=int, default=8192, help='Buffer size for file transfers (default: 4096)')
    
    args = parser.parse_args()
    
    server = FileTransferServer(args.host, args.port, args.dir, args.buffer)
    
    try:
        server.start()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.stop()

if __name__ == "__main__":
    main()