import os
import logging
import socket
import time
import io
from PIL import Image
import pyDes
from typing import Optional, Tuple, List, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('vnc_client')
logger.setLevel(logging.DEBUG)


async def capture_vnc_screen(host: str, port: int, password: str, username: Optional[str] = None,
                             encryption: str = "prefer_on") -> Tuple[bool, Optional[bytes], Optional[str], Optional[Tuple[int, int]]]:
    """Capture a screenshot from a remote machine using VNC.

    Args:
        host: remote machine hostname or IP address
        port: remote machine port
        password: VNC password
        username: username (not used for RFB auth type 2)
        encryption: Encryption preference (default: "prefer_on")

    Returns:
        Tuple containing:
        - success: True if the operation was successful
        - screen_data: PNG image data if successful, None otherwise
        - error_message: Error message if unsuccessful, None otherwise
        - dimensions: Tuple of (width, height) if successful, None otherwise
    """
    logger.debug(f"Connecting to remote machine at {host}:{port} with encryption: {encryption}")

    # Initialize VNC client
    vnc = VNCClient(host=host, port=port, password=password, username=username, encryption=encryption)

    try:
        # Connect to remote machine
        success, error_message = vnc.connect()
        if not success:
            detailed_error = f"Failed to connect to remote machine at {host}:{port}. {error_message}\n"
            detailed_error += "This VNC client supports standard VNC authentication (protocol 2). "
            detailed_error += "Please ensure the remote machine supports this protocol."
            return False, None, detailed_error, None

        # Capture screen
        screen_data = vnc.capture_screen()

        if not screen_data:
            return False, None, f"Failed to capture screenshot from remote machine at {host}:{port}", None

        # Save original dimensions for reference
        original_dims = (vnc.width, vnc.height)

        # Scale the image to FWXGA resolution (1366x768)
        target_width, target_height = 1366, 768

        try:
            # Convert bytes to PIL Image
            image_data = io.BytesIO(screen_data)
            img = Image.open(image_data)

            # Resize the image to the target resolution
            scaled_img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)

            # Convert back to bytes
            output_buffer = io.BytesIO()
            scaled_img.save(output_buffer, format='PNG')
            output_buffer.seek(0)
            scaled_screen_data = output_buffer.getvalue()

            logger.info(f"Scaled image from {original_dims[0]}x{original_dims[1]} to {target_width}x{target_height}")

            # Return success with scaled screen data and target dimensions
            return True, scaled_screen_data, None, (target_width, target_height)

        except Exception as e:
            logger.warning(f"Failed to scale image: {str(e)}. Returning original image.")
            # Return the original image if scaling fails
            return True, screen_data, None, original_dims

    finally:
        # Close VNC connection
        vnc.close()


def encrypt_vnc_password(password: str, challenge: bytes) -> bytes:
    """Encrypt VNC password for RFB authentication.

    Args:
        password: VNC password
        challenge: Challenge bytes from server

    Returns:
        bytes: Encrypted response
    """
    # Convert password to key (truncate to 8 chars or pad with zeros)
    key = password.ljust(8, '\x00')[:8].encode('ascii')

    # VNC uses a reversed bit order for each byte in the key
    reversed_key = bytes([((k >> 0) & 1) << 7 |
                         ((k >> 1) & 1) << 6 |
                         ((k >> 2) & 1) << 5 |
                         ((k >> 3) & 1) << 4 |
                         ((k >> 4) & 1) << 3 |
                         ((k >> 5) & 1) << 2 |
                         ((k >> 6) & 1) << 1 |
                         ((k >> 7) & 1) << 0 for k in key])

    # Create a pyDes instance for encryption
    k = pyDes.des(reversed_key, pyDes.ECB, pad=None)

    # Encrypt the challenge with the key
    result = bytearray()
    for i in range(0, len(challenge), 8):
        block = challenge[i:i+8]
        cipher_block = k.encrypt(block)
        result.extend(cipher_block)

    return bytes(result)

class PixelFormat:
    """VNC pixel format specification."""

    def __init__(self, raw_data: bytes):
        """Parse pixel format from raw data.

        Args:
            raw_data: Raw pixel format data (16 bytes)
        """
        self.bits_per_pixel = raw_data[0]
        self.depth = raw_data[1]
        self.big_endian = raw_data[2] != 0
        self.true_color = raw_data[3] != 0
        self.red_max = int.from_bytes(raw_data[4:6], byteorder='big')
        self.green_max = int.from_bytes(raw_data[6:8], byteorder='big')
        self.blue_max = int.from_bytes(raw_data[8:10], byteorder='big')
        self.red_shift = raw_data[10]
        self.green_shift = raw_data[11]
        self.blue_shift = raw_data[12]
        # Padding bytes 13-15 ignored

    def __str__(self) -> str:
        """Return string representation of pixel format."""
        return (f"PixelFormat(bpp={self.bits_per_pixel}, depth={self.depth}, "
                f"big_endian={self.big_endian}, true_color={self.true_color}, "
                f"rgba_max=({self.red_max},{self.green_max},{self.blue_max}), "
                f"rgba_shift=({self.red_shift},{self.green_shift},{self.blue_shift}))")

class Encoding:
    """VNC encoding types."""
    RAW = 0
    COPY_RECT = 1
    RRE = 2
    HEXTILE = 5
    ZLIB = 6
    TIGHT = 7
    ZRLE = 16
    CURSOR = -239
    DESKTOP_SIZE = -223

class VNCClient:
    """VNC client implementation using standard RFB authentication."""

    def __init__(self, host: str, port: int = 5900, password: Optional[str] = None, username: Optional[str] = None,
                 encryption: str = "prefer_on"):
        """Initialize VNC client with connection parameters.

        Args:
            host: remote machine hostname or IP address
            port: remote machine port (default: 5900)
            password: VNC password (required for RFB auth)
            username: username (not used for RFB auth type 2)
            encryption: Encryption preference (default: "prefer_on")
        """
        self.host = host
        self.port = port
        self.password = password
        self.username = username
        self.encryption = encryption
        self.socket = None
        self.width = 0
        self.height = 0
        self.pixel_format = None
        self.name = ""
        self.protocol_version = ""
        self._last_frame = None
        self._socket_buffer_size = 8192
        logger.debug(f"Initialized VNC client for {host}:{port} with RFB authentication")

    def connect(self) -> Tuple[bool, Optional[str]]:
        """Connect to the remote machine and perform the RFB handshake."""
        try:
            logger.info(f"Attempting connection to remote machine at {self.host}:{self.port}")
            
            # Create socket and connect
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)
            
            try:
                self.socket.connect((self.host, self.port))
                logger.info(f"Successfully established TCP connection to {self.host}:{self.port}")
            except ConnectionRefusedError:
                error_msg = f"Connection refused by {self.host}:{self.port}. Ensure remote machine is running and port is correct."
                logger.error(error_msg)
                return False, error_msg
            except socket.timeout:
                error_msg = f"Connection timed out while trying to connect to {self.host}:{self.port}"
                logger.error(error_msg)
                return False, error_msg

            # Receive RFB protocol version
            try:
                version = self.socket.recv(12).decode('ascii')
                self.protocol_version = version.strip()
                logger.info(f"Server protocol version: {self.protocol_version}")

                if not version.startswith("RFB "):
                    error_msg = f"Invalid protocol version string received: {version}"
                    logger.error(error_msg)
                    return False, error_msg
            except socket.timeout:
                error_msg = "Timeout while waiting for protocol version"
                logger.error(error_msg)
                return False, error_msg

            # Send our protocol version
            our_version = b"RFB 003.008\n"
            logger.debug(f"Sending our protocol version: {our_version.decode('ascii').strip()}")
            self.socket.sendall(our_version)

            # Receive security types
            try:
                security_types_count = self.socket.recv(1)[0]
                logger.info(f"Server offers {security_types_count} security types")

                if security_types_count == 0:
                    # Read error message
                    error_length = int.from_bytes(self.socket.recv(4), byteorder='big')
                    error_message = self.socket.recv(error_length).decode('ascii')
                    error_msg = f"Server rejected connection with error: {error_message}"
                    logger.error(error_msg)
                    return False, error_msg

                # Receive available security types
                security_types = self.socket.recv(security_types_count)
                logger.debug(f"Available security types: {[st for st in security_types]}")

                # Log security type descriptions
                security_type_names = {
                    0: "Invalid",
                    1: "None",
                    2: "VNC Authentication",
                    5: "RA2",
                    6: "RA2ne",
                    16: "Tight",
                    18: "TLS",
                    19: "VeNCrypt",
                    20: "GTK-VNC SASL",
                    21: "MD5 hash authentication",
                    22: "Colin Dean xvp"
                }

                for st in security_types:
                    name = security_type_names.get(st, f"Unknown type {st}")
                    logger.debug(f"Server supports security type {st}: {name}")
            except socket.timeout:
                error_msg = "Timeout while waiting for security types"
                logger.error(error_msg)
                return False, error_msg

            # Choose security type (prefer VeNCrypt, then VNC Authentication)
            chosen_type = None
            if 19 in security_types:
                logger.info("Found VeNCrypt (type 19) - selecting")
                chosen_type = 19
            elif 2 in security_types and self.password:
                logger.info("Found VNC Authentication (type 2) - selecting")
                chosen_type = 2
            elif 1 in security_types:
                logger.info("Found No Authentication (type 1) - selecting")
                chosen_type = 1
            else:
                error_msg = "No supported authentication type available"
                logger.error(error_msg)
                return False, error_msg

            # Send chosen security type
            logger.info(f"Selecting security type: {chosen_type}")
            self.socket.sendall(bytes([chosen_type]))

            # Handle authentication based on chosen type
            if chosen_type == 19:
                # VeNCrypt authentication
                logger.debug("Starting VeNCrypt authentication (type 19)")
                success, error_msg = self._handle_vencrypt_auth()
                if not success:
                    return False, error_msg
                    
            elif chosen_type == 2:
                # VNC Authentication
                logger.debug("Starting VNC authentication (type 2)")
                if not self.password:
                    error_msg = "Password required for VNC authentication"
                    logger.error(error_msg)
                    return False, error_msg

                try:
                    # Receive 16-byte challenge
                    challenge = self.socket.recv(16)
                    if len(challenge) != 16:
                        error_msg = f"Invalid challenge received: expected 16 bytes, got {len(challenge)}"
                        logger.error(error_msg)
                        return False, error_msg

                    logger.debug("Received 16-byte challenge from server")

                    # Encrypt password with challenge using DES
                    response = encrypt_vnc_password(self.password, challenge)
                    
                    # Send encrypted response
                    self.socket.sendall(response)
                    logger.debug("Sent encrypted password response")

                    # Check authentication result
                    auth_result = int.from_bytes(self.socket.recv(4), byteorder='big')
                    
                    if auth_result != 0:
                        # Read error message if available
                        try:
                            error_length = int.from_bytes(self.socket.recv(4), byteorder='big')
                            error_message = self.socket.recv(error_length).decode('ascii')
                            error_msg = f"VNC authentication failed: {error_message}"
                        except:
                            error_msg = f"VNC authentication failed with code: {auth_result}"
                        
                        logger.error(error_msg)
                        return False, error_msg

                    logger.info("VNC authentication successful")

                except Exception as e:
                    error_msg = f"Error during VNC authentication: {str(e)}"
                    logger.error(error_msg)
                    return False, error_msg

            elif chosen_type == 1:
                # No authentication required
                logger.info("No authentication required")

            # Send client init (shared flag)
            logger.debug("Sending client init with shared flag")
            self.socket.sendall(b'\x01')  # non-zero = shared

            # Receive server init
            logger.debug("Waiting for server init message")
            server_init_header = self.socket.recv(24)
            if len(server_init_header) < 24:
                error_msg = f"Incomplete server init header received"
                logger.error(error_msg)
                return False, error_msg

            # Parse server init
            self.width = int.from_bytes(server_init_header[0:2], byteorder='big')
            self.height = int.from_bytes(server_init_header[2:4], byteorder='big')
            self.pixel_format = PixelFormat(server_init_header[4:20])

            name_length = int.from_bytes(server_init_header[20:24], byteorder='big')
            logger.debug(f"Server reports desktop size: {self.width}x{self.height}")

            if name_length > 0:
                name_data = self.socket.recv(name_length)
                self.name = name_data.decode('utf-8', errors='replace')
                logger.debug(f"Server name: {self.name}")

            logger.info(f"Successfully connected to remote machine: {self.name}")
            logger.debug(f"Screen dimensions: {self.width}x{self.height}")

            # Set preferred pixel format and encodings
            self._set_pixel_format()
            self._set_encodings([Encoding.RAW, Encoding.COPY_RECT, Encoding.DESKTOP_SIZE])

            logger.info("VNC connection fully established")
            return True, None

        except Exception as e:
            error_msg = f"Unexpected error during VNC connection: {str(e)}"
            logger.error(error_msg, exc_info=True)
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None
            return False, error_msg

    def _handle_vencrypt_auth(self) -> Tuple[bool, Optional[str]]:
        """Handle VeNCrypt authentication (security type 19)."""
        try:
            # VeNCrypt handshake - receive version
            vencrypt_version = self.socket.recv(2)
            if len(vencrypt_version) != 2:
                return False, "Failed to receive VeNCrypt version"
            
            major_version = vencrypt_version[0]
            minor_version = vencrypt_version[1]
            logger.debug(f"VeNCrypt version: {major_version}.{minor_version}")
            
            # Send our supported version (0.2)
            self.socket.sendall(b'\x00\x02')
            
            # Receive server's chosen version
            chosen_version = self.socket.recv(2)
            if len(chosen_version) != 2:
                return False, "Failed to receive VeNCrypt chosen version"
                
            if chosen_version != b'\x00\x02':
                return False, f"Unsupported VeNCrypt version: {chosen_version[0]}.{chosen_version[1]}"
            
            logger.debug("VeNCrypt version 0.2 negotiated")
            
            # Receive number of sub-authentication types
            num_subtypes = self.socket.recv(1)[0]
            if num_subtypes == 0:
                return False, "No VeNCrypt sub-authentication types available"
            
            logger.debug(f"Server offers {num_subtypes} VeNCrypt sub-types")
            
            # Receive sub-authentication types (4 bytes each)
            subtypes_data = self.socket.recv(num_subtypes * 4)
            if len(subtypes_data) != num_subtypes * 4:
                return False, "Failed to receive VeNCrypt sub-types"
            
            # Parse sub-authentication types
            subtypes = []
            for i in range(num_subtypes):
                subtype = int.from_bytes(subtypes_data[i*4:(i+1)*4], byteorder='big')
                subtypes.append(subtype)
            
            # VeNCrypt sub-authentication types
            vencrypt_subtypes = {
                256: "Plain",
                257: "TLSNone", 
                258: "TLSVnc",
                259: "TLSPlain",
                260: "X509None",
                261: "X509Vnc", 
                262: "X509Plain",
                263: "X509SASL",
                264: "TlsSASL"
            }
            
            for subtype in subtypes:
                name = vencrypt_subtypes.get(subtype, f"Unknown subtype {subtype}")
                logger.debug(f"Server supports VeNCrypt subtype {subtype}: {name}")
            
            # Choose a sub-authentication type we support
            chosen_subtype = None
            
            # Prefer encrypted types with VNC authentication
            if 258 in subtypes and self.password:  # TLSVnc
                chosen_subtype = 258
                logger.info("Selecting TLSVnc sub-authentication")
            elif 261 in subtypes and self.password:  # X509Vnc
                chosen_subtype = 261
                logger.info("Selecting X509Vnc sub-authentication")
            elif 257 in subtypes:  # TLSNone
                chosen_subtype = 257
                logger.info("Selecting TLSNone sub-authentication")
            elif 256 in subtypes and self.password:  # Plain
                chosen_subtype = 256
                logger.info("Selecting Plain sub-authentication")
            else:
                return False, "No supported VeNCrypt sub-authentication type available"
            
            # Send chosen sub-authentication type
            self.socket.sendall(chosen_subtype.to_bytes(4, byteorder='big'))
            
            # Handle TLS/SSL setup for encrypted subtypes
            if chosen_subtype in [257, 258, 259, 260, 261, 262, 263, 264]:
                success, error_msg = self._setup_tls_connection()
                if not success:
                    return False, error_msg
            
            # Handle the actual authentication based on subtype
            if chosen_subtype in [258, 261]:  # TLSVnc or X509Vnc
                # Standard VNC authentication over TLS
                return self._handle_vnc_auth_over_tls()
            elif chosen_subtype in [256]:  # Plain
                # Plain text authentication
                return self._handle_plain_auth()
            elif chosen_subtype in [257, 260]:  # TLSNone or X509None
                # No authentication required (already encrypted)
                logger.info("No authentication required (encrypted connection)")
                return True, None
            else:
                return False, f"Unsupported VeNCrypt subtype: {chosen_subtype}"
                
        except Exception as e:
            return False, f"Error during VeNCrypt authentication: {str(e)}"
    
    def _setup_tls_connection(self) -> Tuple[bool, Optional[str]]:
        """Setup TLS/SSL connection for VeNCrypt."""
        try:
            import ssl
            
            # Create SSL context
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE  # Don't verify certificates for now
            
            # Wrap the socket with TLS
            self.socket = context.wrap_socket(self.socket, server_hostname=self.host)
            logger.debug("TLS connection established")
            
            return True, None
            
        except ImportError:
            return False, "SSL module not available for TLS connection"
        except Exception as e:
            return False, f"Failed to establish TLS connection: {str(e)}"
    
    def _handle_vnc_auth_over_tls(self) -> Tuple[bool, Optional[str]]:
        """Handle VNC authentication over TLS connection."""
        try:
            if not self.password:
                return False, "Password required for VNC authentication"
            
            # Receive 16-byte challenge
            challenge = self.socket.recv(16)
            if len(challenge) != 16:
                return False, f"Invalid challenge received: expected 16 bytes, got {len(challenge)}"
            
            logger.debug("Received 16-byte challenge from server (over TLS)")
            
            # Encrypt password with challenge using DES
            response = encrypt_vnc_password(self.password, challenge)
            
            # Send encrypted response
            self.socket.sendall(response)
            logger.debug("Sent encrypted password response (over TLS)")
            
            # Check authentication result
            auth_result = int.from_bytes(self.socket.recv(4), byteorder='big')
            
            if auth_result != 0:
                try:
                    error_length = int.from_bytes(self.socket.recv(4), byteorder='big')
                    error_message = self.socket.recv(error_length).decode('ascii')
                    error_msg = f"VNC authentication failed: {error_message}"
                except:
                    error_msg = f"VNC authentication failed with code: {auth_result}"
                
                logger.error(error_msg)
                return False, error_msg
            
            logger.info("VNC authentication over TLS successful")
            return True, None
            
        except Exception as e:
            return False, f"Error during VNC authentication over TLS: {str(e)}"
    
    def _handle_plain_auth(self) -> Tuple[bool, Optional[str]]:
        """Handle plain text authentication for VeNCrypt."""
        try:
            if not self.username or not self.password:
                return False, "Username and password required for plain authentication"
            
            # Send username length + username
            username_bytes = self.username.encode('utf-8')
            self.socket.sendall(len(username_bytes).to_bytes(4, byteorder='big'))
            self.socket.sendall(username_bytes)
            
            # Send password length + password  
            password_bytes = self.password.encode('utf-8')
            self.socket.sendall(len(password_bytes).to_bytes(4, byteorder='big'))
            self.socket.sendall(password_bytes)
            
            logger.debug("Sent plain authentication credentials")
            
            # Check authentication result
            auth_result = int.from_bytes(self.socket.recv(4), byteorder='big')
            
            if auth_result != 0:
                try:
                    error_length = int.from_bytes(self.socket.recv(4), byteorder='big')
                    error_message = self.socket.recv(error_length).decode('ascii')
                    error_msg = f"Plain authentication failed: {error_message}"
                except:
                    error_msg = f"Plain authentication failed with code: {auth_result}"
                
                logger.error(error_msg)
                return False, error_msg
            
            logger.info("Plain authentication successful")
            return True, None
            
        except Exception as e:
            return False, f"Error during plain authentication: {str(e)}"

    def _set_pixel_format(self):
        """Set the pixel format to be used for the connection (32-bit true color)."""
        try:
            message = bytearray([0])  # message type 0 = SetPixelFormat
            message.extend([0, 0, 0])  # padding

            # Pixel format (16 bytes)
            message.extend([
                32,  # bits-per-pixel
                24,  # depth
                1,   # big-endian flag (1 = true)
                1,   # true-color flag (1 = true)
                0, 255,  # red-max (255)
                0, 255,  # green-max (255)
                0, 255,  # blue-max (255)
                16,  # red-shift
                8,   # green-shift
                0,   # blue-shift
                0, 0, 0  # padding
            ])

            self.socket.sendall(message)
            logger.debug("Set pixel format to 32-bit true color")
        except Exception as e:
            logger.error(f"Error setting pixel format: {str(e)}")

    def _set_encodings(self, encodings: List[int]):
        """Set the encodings to be used for the connection."""
        try:
            message = bytearray([2])  # message type 2 = SetEncodings
            message.extend([0])  # padding

            # Number of encodings
            message.extend(len(encodings).to_bytes(2, byteorder='big'))

            # Encodings
            for encoding in encodings:
                message.extend(encoding.to_bytes(4, byteorder='big', signed=True))

            self.socket.sendall(message)
            logger.debug(f"Set encodings: {encodings}")
        except Exception as e:
            logger.error(f"Error setting encodings: {str(e)}")

    def _decode_raw_rect(self, rect_data: bytes, x: int, y: int, width: int, height: int,
                        img: Image.Image) -> None:
        """Decode a RAW-encoded rectangle and draw it to the image."""
        try:
            # Create a new image from the raw data
            if self.pixel_format.bits_per_pixel == 32:
                # 32-bit color (RGBA)
                raw_img = Image.frombytes('RGBA', (width, height), rect_data)
                # Convert to RGB if needed
                if raw_img.mode != 'RGB':
                    raw_img = raw_img.convert('RGB')
            elif self.pixel_format.bits_per_pixel == 16:
                # 16-bit color needs special handling
                raw_img = Image.new('RGB', (width, height))
                pixels = raw_img.load()

                for i in range(height):
                    for j in range(width):
                        idx = (i * width + j) * 2
                        pixel = int.from_bytes(rect_data[idx:idx+2],
                                            byteorder='big' if self.pixel_format.big_endian else 'little')

                        r = ((pixel >> self.pixel_format.red_shift) & self.pixel_format.red_max)
                        g = ((pixel >> self.pixel_format.green_shift) & self.pixel_format.green_max)
                        b = ((pixel >> self.pixel_format.blue_shift) & self.pixel_format.blue_max)

                        # Scale values to 0-255 range
                        r = int(r * 255 / self.pixel_format.red_max)
                        g = int(g * 255 / self.pixel_format.green_max)
                        b = int(b * 255 / self.pixel_format.blue_max)

                        pixels[j, i] = (r, g, b)
            else:
                # Fallback for other bit depths
                raw_img = Image.new('RGB', (width, height), color='black')
                logger.warning(f"Unsupported pixel format: {self.pixel_format.bits_per_pixel}-bit")

            # Paste the decoded image onto the target image
            img.paste(raw_img, (x, y))

        except Exception as e:
            logger.error(f"Error decoding RAW rectangle: {str(e)}")
            # Fill with error color on failure
            raw_img = Image.new('RGB', (width, height), color='red')
            img.paste(raw_img, (x, y))

    def _decode_copy_rect(self, rect_data: bytes, x: int, y: int, width: int, height: int,
                         img: Image.Image) -> None:
        """Decode a COPY_RECT-encoded rectangle and draw it to the image."""
        try:
            src_x = int.from_bytes(rect_data[0:2], byteorder='big')
            src_y = int.from_bytes(rect_data[2:4], byteorder='big')

            # Copy the region from the image itself
            region = img.crop((src_x, src_y, src_x + width, src_y + height))
            img.paste(region, (x, y))

        except Exception as e:
            logger.error(f"Error decoding COPY_RECT rectangle: {str(e)}")
            # Fill with error color on failure
            raw_img = Image.new('RGB', (width, height), color='blue')
            img.paste(raw_img, (x, y))

    def capture_screen(self) -> Optional[bytes]:
        """Capture a screenshot from the remote machine."""
        try:
            if not self.socket:
                logger.error("Not connected to remote machine")
                return None

            # Use incremental updates if we have a previous frame
            is_incremental = self._last_frame is not None

            # Create or reuse image
            if is_incremental:
                img = self._last_frame
            else:
                img = Image.new('RGB', (self.width, self.height), color='black')

            # Send FramebufferUpdateRequest message
            msg = bytearray([3])  # message type 3 = FramebufferUpdateRequest
            msg.extend([1 if is_incremental else 0])  # incremental flag
            msg.extend(int(0).to_bytes(2, byteorder='big'))  # x-position
            msg.extend(int(0).to_bytes(2, byteorder='big'))  # y-position
            msg.extend(int(self.width).to_bytes(2, byteorder='big'))  # width
            msg.extend(int(self.height).to_bytes(2, byteorder='big'))  # height

            self.socket.sendall(msg)

            # Receive FramebufferUpdate message header
            header = self._recv_exact(4)
            if not header or header[0] != 0:  # 0 = FramebufferUpdate
                logger.error(f"Unexpected message type in response: {header[0] if header else 'None'}")
                return None

            # Read number of rectangles
            num_rects = int.from_bytes(header[2:4], byteorder='big')
            logger.debug(f"Received {num_rects} rectangles")

            # Process each rectangle
            for rect_idx in range(num_rects):
                # Read rectangle header
                rect_header = self._recv_exact(12)
                if not rect_header:
                    logger.error("Failed to read rectangle header")
                    return None

                x = int.from_bytes(rect_header[0:2], byteorder='big')
                y = int.from_bytes(rect_header[2:4], byteorder='big')
                width = int.from_bytes(rect_header[4:6], byteorder='big')
                height = int.from_bytes(rect_header[6:8], byteorder='big')
                encoding_type = int.from_bytes(rect_header[8:12], byteorder='big', signed=True)

                if encoding_type == Encoding.RAW:
                    pixel_size = self.pixel_format.bits_per_pixel // 8
                    data_size = width * height * pixel_size

                    rect_data = self._recv_exact(data_size)
                    if not rect_data or len(rect_data) != data_size:
                        logger.error(f"Failed to read RAW rectangle data")
                        return None

                    self._decode_raw_rect(rect_data, x, y, width, height, img)

                elif encoding_type == Encoding.COPY_RECT:
                    rect_data = self._recv_exact(4)
                    if not rect_data:
                        logger.error("Failed to read COPY_RECT data")
                        return None
                    self._decode_copy_rect(rect_data, x, y, width, height, img)

                elif encoding_type == Encoding.DESKTOP_SIZE:
                    logger.debug(f"Desktop size changed to {width}x{height}")
                    self.width = width
                    self.height = height
                    new_img = Image.new('RGB', (self.width, self.height), color='black')
                    new_img.paste(img, (0, 0))
                    img = new_img
                else:
                    logger.warning(f"Unsupported encoding type: {encoding_type}")
                    continue

            # Store the frame for future incremental updates
            self._last_frame = img

            # Convert image to PNG
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG', optimize=True, quality=95)
            img_byte_arr.seek(0)

            return img_byte_arr.getvalue()

        except Exception as e:
            logger.error(f"Error capturing screen: {str(e)}")
            return None

    def _recv_exact(self, size: int) -> Optional[bytes]:
        """Receive exactly size bytes from the socket."""
        try:
            data = bytearray()
            while len(data) < size:
                chunk = self.socket.recv(min(self._socket_buffer_size, size - len(data)))
                if not chunk:
                    return None
                data.extend(chunk)
            return bytes(data)
        except Exception as e:
            logger.error(f"Error receiving data: {str(e)}")
            return None

    def close(self):
        """Close the connection to the remote machine."""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None

    def send_key_event(self, key: int, down: bool) -> bool:
        """Send a key event to the remote machine."""
        try:
            if not self.socket:
                logger.error("Not connected to remote machine")
                return False

            # Message type 4 = KeyEvent
            message = bytearray([4])
            message.extend([1 if down else 0])  # Down flag
            message.extend([0, 0])  # Padding
            message.extend(key.to_bytes(4, byteorder='big'))  # Key

            logger.debug(f"Sending KeyEvent: key=0x{key:08x}, down={down}")
            self.socket.sendall(message)
            return True

        except Exception as e:
            logger.error(f"Error sending key event: {str(e)}")
            return False

    def send_pointer_event(self, x: int, y: int, button_mask: int) -> bool:
        """Send a pointer (mouse) event to the remote machine."""
        try:
            if not self.socket:
                logger.error("Not connected to remote machine")
                return False

            # Ensure coordinates are within framebuffer bounds
            x = max(0, min(x, self.width - 1))
            y = max(0, min(y, self.height - 1))

            # Message type 5 = PointerEvent
            message = bytearray([5])
            message.extend([button_mask & 0xFF])  # Button mask
            message.extend(x.to_bytes(2, byteorder='big'))  # X position
            message.extend(y.to_bytes(2, byteorder='big'))  # Y position

            logger.debug(f"Sending PointerEvent: x={x}, y={y}, button_mask={button_mask:08b}")
            self.socket.sendall(message)
            return True

        except Exception as e:
            logger.error(f"Error sending pointer event: {str(e)}")
            return False

    def send_mouse_click(self, x: int, y: int, button: int = 1, double_click: bool = False, delay_ms: int = 100) -> bool:
        """Send a mouse click at the specified position."""
        try:
            if not self.socket:
                logger.error("Not connected to remote machine")
                return False

            # Calculate button mask
            button_mask = 1 << (button - 1)

            # Move mouse to position first
            if not self.send_pointer_event(x, y, 0):
                return False

            # Press button
            if not self.send_pointer_event(x, y, button_mask):
                return False

            # Wait
            time.sleep(delay_ms / 1000.0)

            # Release button
            if not self.send_pointer_event(x, y, 0):
                return False

            # If double click, perform second click
            if double_click:
                time.sleep(delay_ms / 1000.0)
                if not self.send_pointer_event(x, y, button_mask):
                    return False
                time.sleep(delay_ms / 1000.0)
                if not self.send_pointer_event(x, y, 0):
                    return False

            return True

        except Exception as e:
            logger.error(f"Error sending mouse click: {str(e)}")
            return False

    def send_text(self, text: str) -> bool:
        """Send text as a series of key press/release events."""
        try:
            if not self.socket:
                logger.error("Not connected to remote machine")
                return False

            success = True

            for char in text:
                # Special key mapping
                if char == '\n' or char == '\r':  # Return/Enter
                    key = 0xff0d
                elif char == '\t':  # Tab
                    key = 0xff09
                elif char == '\b':  # Backspace
                    key = 0xff08
                elif char == ' ':  # Space
                    key = 0x20
                else:
                    key = ord(char)

                # Handle uppercase letters and special characters
                need_shift = char.isupper() or char in '~!@#$%^&*()_+{}|:"<>?'

                if need_shift:
                    if not self.send_key_event(0xffe1, True):  # Press shift
                        success = False
                        break

                # Press and release key
                if not self.send_key_event(key, True):
                    success = False
                    break
                if not self.send_key_event(key, False):
                    success = False
                    break

                if need_shift:
                    if not self.send_key_event(0xffe1, False):  # Release shift
                        success = False
                        break

                # Small delay between keys
                time.sleep(0.01)

            return success

        except Exception as e:
            logger.error(f"Error sending text: {str(e)}")
            return False

    def send_key_combination(self, keys: List[int]) -> bool:
        """Send a key combination (e.g., Ctrl+Alt+Delete)."""
        try:
            if not self.socket:
                logger.error("Not connected to remote machine")
                return False

            # Press all keys in sequence
            for key in keys:
                if not self.send_key_event(key, True):
                    return False

            # Release all keys in reverse order
            for key in reversed(keys):
                if not self.send_key_event(key, False):
                    return False

            return True

        except Exception as e:
            logger.error(f"Error sending key combination: {str(e)}")
            return False