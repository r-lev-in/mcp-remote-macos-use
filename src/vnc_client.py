#!/usr/bin/env python3
"""
PiKVM API Client for Remote Control Operations

This client implements the PiKVM API for screen capture and remote control
based on the documentation at https://docs.pikvm.org/api/

Requirements:
    pip install requests pillow
"""

import requests
import base64
import time
import io
from PIL import Image
from typing import Optional, Tuple, Dict, Any, List
import logging
import json
from urllib.parse import urljoin

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('pikvm_client')
logger.setLevel(logging.DEBUG)


async def capture_vnc_screen(host: str, port: int, password: str, username: Optional[str] = None,
                             encryption: str = "prefer_on") -> Tuple[bool, Optional[bytes], Optional[str], Optional[Tuple[int, int]]]:
    """Capture a screenshot from a remote MacOs machine.

    Args:
        host: remote MacOs machine hostname or IP address
        port: remote MacOs machine port
        password: remote MacOs machine password
        username: remote MacOs machine username (optional)
        encryption: Encryption preference (default: "prefer_on")

    Returns:
        Tuple containing:
        - success: True if the operation was successful
        - screen_data: PNG image data if successful, None otherwise
        - error_message: Error message if unsuccessful, None otherwise
        - dimensions: Tuple of (width, height) if successful, None otherwise
    """
    logger.debug(f"Connecting to remote MacOs machine at {host}:{port} with encryption: {encryption}")

    # Initialize VNC client (now using PiKVM API)
    vnc = VNCClient(host=host, port=port, password=password, username=username)

    try:
        # Connect to remote machine
        success, error_message = vnc.connect()
        if not success:
            detailed_error = f"Failed to connect to remote machine at {host}:{port}. {error_message}\n"
            detailed_error += "This client now uses PiKVM API. "
            detailed_error += "Please ensure the remote machine is running PiKVM."
            return False, None, detailed_error, None

        # Capture screen
        success, screen_data, error_message, dimensions = vnc.capture_screen()

        if not success:
            return False, None, f"Failed to capture screenshot from remote machine at {host}:{port}: {error_message}", None

        # Scale the image to FWXGA resolution (1366x768) if needed
        target_width, target_height = 1366, 768

        try:
            if dimensions and (dimensions[0] != target_width or dimensions[1] != target_height):
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

                logger.info(f"Scaled image from {dimensions[0]}x{dimensions[1]} to {target_width}x{target_height}")

                # Return success with scaled screen data and target dimensions
                return True, scaled_screen_data, None, (target_width, target_height)
            else:
                # Return original image if no scaling needed
                return True, screen_data, None, dimensions

        except Exception as e:
            logger.warning(f"Failed to scale image: {str(e)}. Returning original image.")
            # Return the original image if scaling fails
            return True, screen_data, None, dimensions

    finally:
        # Close VNC connection
        vnc.close()


class VNCClient:
    """PiKVM API client for remote control operations."""
    
    def __init__(self, host: str, username: str = "admin", password: str = "admin", 
                 port: int = 443, use_https: bool = True):
        """
        Initialize PiKVM client.
        
        Args:
            host: PiKVM hostname or IP address
            username: PiKVM username (default: admin)
            password: PiKVM password (default: admin)
            port: PiKVM port (default: 443 for HTTPS, 80 for HTTP)
            use_https: Whether to use HTTPS (default: True)
        """
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.use_https = use_https
        
        # Build base URL
        protocol = "https" if use_https else "http"
        self.base_url = f"{protocol}://{host}:{port}"
        
        # Setup session with authentication
        self.session = requests.Session()
        self.session.auth = (username, password)
        self.session.verify = False  # Disable SSL verification for self-signed certs
        
        # Disable SSL warnings
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # Initialize properties for compatibility
        self.width = 0
        self.height = 0
        self.pixel_format = None
        self.name = ""
        self.protocol_version = ""
        self._last_frame = None
        self._socket_buffer_size = 8192
        
        logger.info(f"Initialized PiKVM client for {self.base_url}")
    
    def test_connection(self) -> Tuple[bool, Optional[str]]:
        """
        Test connection to PiKVM server.
        
        Returns:
            Tuple of (success, error_message)
        """
        try:
            logger.debug("Testing connection to PiKVM server")
            response = self.session.get(
                urljoin(self.base_url, "/api/info"),
                timeout=10
            )
            
            if response.status_code == 200:
                info = response.json()
                logger.info(f"Successfully connected to PiKVM")
                logger.debug(f"Server info: {info}")
                return True, None
            else:
                error_msg = f"Connection failed with status {response.status_code}"
                logger.error(error_msg)
                return False, error_msg
                
        except requests.exceptions.ConnectTimeout:
            error_msg = f"Connection timeout to {self.base_url}"
            logger.error(error_msg)
            return False, error_msg
        except requests.exceptions.ConnectionError as e:
            error_msg = f"Connection error to {self.base_url}: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Unexpected error during connection test: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    def get_server_info(self) -> Optional[Dict[str, Any]]:
        """
        Get server information.
        
        Returns:
            Dictionary with server info or None if failed
        """
        try:
            response = self.session.get(urljoin(self.base_url, "/api/info"))
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get server info: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error getting server info: {str(e)}")
            return None
    
    def capture_screen(self, quality: int = 80) -> Tuple[bool, Optional[bytes], Optional[str], Optional[Tuple[int, int]]]:
        """
        Capture screenshot from PiKVM.
        
        Args:
            quality: JPEG quality (1-100, default: 80)
            
        Returns:
            Tuple of (success, image_data, error_message, dimensions)
        """
        try:
            logger.debug(f"Capturing screen with quality {quality}")
            
            # Get screenshot from PiKVM API
            response = self.session.get(
                urljoin(self.base_url, f"/api/streamer/snapshot?quality={quality}"),
                timeout=30
            )
            
            if response.status_code == 200:
                # PiKVM returns JPEG image data
                image_data = response.content
                
                # Get image dimensions and update instance properties
                try:
                    img = Image.open(io.BytesIO(image_data))
                    dimensions = img.size
                    self.width = dimensions[0]  # Update instance property
                    self.height = dimensions[1]  # Update instance property
                    logger.info(f"Screenshot captured: {dimensions[0]}x{dimensions[1]}")
                    
                    # Convert to PNG for consistency
                    png_buffer = io.BytesIO()
                    img.save(png_buffer, format='PNG')
                    png_data = png_buffer.getvalue()
                    
                    return True, png_data, None, dimensions
                    
                except Exception as e:
                    logger.error(f"Error processing image: {str(e)}")
                    return False, None, f"Error processing image: {str(e)}", None
            else:
                error_msg = f"Screenshot capture failed with status {response.status_code}"
                logger.error(error_msg)
                return False, None, error_msg, None
                
        except requests.exceptions.Timeout:
            error_msg = "Screenshot capture timed out"
            logger.error(error_msg)
            return False, None, error_msg, None
        except Exception as e:
            error_msg = f"Error capturing screenshot: {str(e)}"
            logger.error(error_msg)
            return False, None, error_msg, None
    
    def send_key_event(self, key: str, state: bool = True) -> bool:
        """
        Send keyboard event.
        
        Args:
            key: Key name (e.g., 'a', 'Enter', 'Ctrl', etc.)
            state: True for press, False for release
            
        Returns:
            True if successful
        """
        try:
            payload = {
                "key": key,
                "state": state
            }
            
            response = self.session.post(
                urljoin(self.base_url, "/api/hid/events/send_key"),
                json=payload
            )
            
            if response.status_code == 200:
                logger.debug(f"Key event sent: {key} = {state}")
                return True
            else:
                logger.error(f"Key event failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending key event: {str(e)}")
            return False
    
    def send_key_press(self, key: str, hold_time: float = 0.1) -> bool:
        """
        Send key press and release.
        
        Args:
            key: Key name
            hold_time: Time to hold key in seconds
            
        Returns:
            True if successful
        """
        try:
            # Press key
            if not self.send_key_event(key, True):
                return False
            
            # Hold
            time.sleep(hold_time)
            
            # Release key
            if not self.send_key_event(key, False):
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending key press: {str(e)}")
            return False
    
    def send_text(self, text: str) -> bool:
        """
        Send text by typing individual characters.
        
        Args:
            text: Text to type
            
        Returns:
            True if successful
        """
        try:
            for char in text:
                if not self.send_key_press(char, 0.05):
                    return False
                time.sleep(0.02)  # Small delay between characters
            
            logger.debug(f"Text sent: {text}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending text: {str(e)}")
            return False
    
    def send_key_combination(self, keys: List[str]) -> bool:
        """
        Send key combination (e.g., Ctrl+Alt+Delete).
        
        Args:
            keys: List of key names to press together
            
        Returns:
            True if successful
        """
        try:
            # Press all keys
            for key in keys:
                if not self.send_key_event(key, True):
                    return False
                time.sleep(0.05)
            
            # Hold briefly
            time.sleep(0.1)
            
            # Release all keys in reverse order
            for key in reversed(keys):
                if not self.send_key_event(key, False):
                    return False
                time.sleep(0.05)
            
            logger.debug(f"Key combination sent: {'+'.join(keys)}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending key combination: {str(e)}")
            return False
    
    def send_mouse_event(self, x: int, y: int, button: Optional[str] = None, 
                        state: Optional[bool] = None) -> bool:
        """
        Send mouse event.
        
        Args:
            x: X coordinate
            y: Y coordinate  
            button: Mouse button ('left', 'right', 'middle') or None for move
            state: True for press, False for release, None for move
            
        Returns:
            True if successful
        """
        try:
            payload = {
                "x": x,
                "y": y
            }
            
            if button and state is not None:
                payload["button"] = button
                payload["state"] = state
            
            endpoint = "/api/hid/events/send_mouse_button" if button else "/api/hid/events/send_mouse_move"
            
            response = self.session.post(
                urljoin(self.base_url, endpoint),
                json=payload
            )
            
            if response.status_code == 200:
                logger.debug(f"Mouse event sent: x={x}, y={y}, button={button}, state={state}")
                return True
            else:
                logger.error(f"Mouse event failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending mouse event: {str(e)}")
            return False
    
    def send_mouse_move(self, x: int, y: int) -> bool:
        """
        Move mouse to coordinates.
        
        Args:
            x: X coordinate
            y: Y coordinate
            
        Returns:
            True if successful
        """
        return self.send_mouse_event(x, y)
    
    def send_mouse_click(self, x: int, y: int, button: str = "left", 
                        double_click: bool = False, delay: float = 0.1) -> bool:
        """
        Send mouse click at coordinates.
        
        Args:
            x: X coordinate
            y: Y coordinate
            button: Mouse button ('left', 'right', 'middle')
            double_click: Whether to double-click
            delay: Delay between press and release
            
        Returns:
            True if successful
        """
        try:
            # Move to position
            if not self.send_mouse_move(x, y):
                return False
            
            # First click
            if not self.send_mouse_event(x, y, button, True):
                return False
            
            time.sleep(delay)
            
            if not self.send_mouse_event(x, y, button, False):
                return False
            
            # Second click for double-click
            if double_click:
                time.sleep(delay)
                
                if not self.send_mouse_event(x, y, button, True):
                    return False
                
                time.sleep(delay)
                
                if not self.send_mouse_event(x, y, button, False):
                    return False
            
            logger.debug(f"Mouse click sent: x={x}, y={y}, button={button}, double={double_click}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending mouse click: {str(e)}")
            return False
    
    def send_mouse_scroll(self, x: int, y: int, direction: str) -> bool:
        """
        Send mouse scroll event.
        
        Args:
            x: X coordinate
            y: Y coordinate
            direction: Scroll direction ('up' or 'down')
            
        Returns:
            True if successful
        """
        try:
            payload = {
                "x": x,
                "y": y,
                "direction": direction
            }
            
            response = self.session.post(
                urljoin(self.base_url, "/api/hid/events/send_mouse_wheel"),
                json=payload
            )
            
            if response.status_code == 200:
                logger.debug(f"Mouse scroll sent: x={x}, y={y}, direction={direction}")
                return True
            else:
                logger.error(f"Mouse scroll failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending mouse scroll: {str(e)}")
            return False
    
    def get_stream_info(self) -> Optional[Dict[str, Any]]:
        """
        Get video stream information.
        
        Returns:
            Dictionary with stream info or None if failed
        """
        try:
            response = self.session.get(urljoin(self.base_url, "/api/streamer"))
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get stream info: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error getting stream info: {str(e)}")
            return None
    
    def _set_pixel_format(self):
        """Set the pixel format (compatibility method for PiKVM - no-op)."""
        logger.debug("_set_pixel_format called (no-op for PiKVM)")
        pass
    
    def _set_encodings(self, encodings):
        """Set encodings (compatibility method for PiKVM - no-op)."""
        logger.debug(f"_set_encodings called with {encodings} (no-op for PiKVM)")
        pass
    
    def _recv_exact(self, size: int):
        """Receive exact bytes (compatibility method for PiKVM - no-op)."""
        logger.debug(f"_recv_exact called for {size} bytes (no-op for PiKVM)")
        return None
    
    def _decode_raw_rect(self, rect_data, x, y, width, height, img):
        """Decode raw rectangle (compatibility method for PiKVM - no-op)."""
        logger.debug("_decode_raw_rect called (no-op for PiKVM)")
        pass
    
    def _decode_copy_rect(self, rect_data, x, y, width, height, img):
        """Decode copy rectangle (compatibility method for PiKVM - no-op)."""
        logger.debug("_decode_copy_rect called (no-op for PiKVM)")
        pass
    
    def connect(self) -> Tuple[bool, Optional[str]]:
        """Connect to PiKVM (renamed from test_connection for compatibility)."""
        return self.test_connection()

    def close(self):
        """Close connection (compatibility method for PiKVM - no-op)."""
        logger.debug("close called (no-op for PiKVM)")
        pass
    
    def reset_hid(self) -> bool:
        """
        Reset HID (keyboard/mouse) devices.
        
        Returns:
            True if successful
        """
        try:
            response = self.session.post(urljoin(self.base_url, "/api/hid/reset"))
            
            if response.status_code == 200:
                logger.info("HID devices reset successfully")
                return True
            else:
                logger.error(f"HID reset failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error resetting HID: {str(e)}")
            return False
        """
        Reset HID (keyboard/mouse) devices.
        
        Returns:
            True if successful
        """
        try:
            response = self.session.post(urljoin(self.base_url, "/api/hid/reset"))
            
            if response.status_code == 200:
                logger.info("HID devices reset successfully")
                return True
            else:
                logger.error(f"HID reset failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error resetting HID: {str(e)}")
            return False


# Wrapper functions to match the original VNC interface
async def capture_pikvm_screen(host: str, port: int, username: str, password: str) -> Tuple[bool, Optional[bytes], Optional[str], Optional[Tuple[int, int]]]:
    """
    Capture screenshot from PiKVM (async wrapper for compatibility).
    
    Args:
        host: PiKVM hostname or IP
        port: PiKVM port  
        username: PiKVM username
        password: PiKVM password
        
    Returns:
        Tuple of (success, image_data, error_message, dimensions)
    """
    client = VNCClient(host=host, port=port, username=username, password=password)
    
    # Test connection first
    success, error = client.test_connection()
    if not success:
        return False, None, error, None
    
    # Capture screen
    return client.capture_screen()


def main():
    """Example usage of PiKVM client."""
    
    # Configuration
    HOST = "192.168.88.138"
    PORT = 443
    USERNAME = "admin"
    PASSWORD = "admin"
    
    # Initialize client
    client = VNCClient(host=HOST, port=PORT, username=USERNAME, password=PASSWORD)
    
    # Test connection
    print("Testing connection...")
    success, error = client.test_connection()
    if not success:
        print(f"Connection failed: {error}")
        return
    
    print("Connection successful!")
    
    # Get server info
    info = client.get_server_info()
    if info:
        print(f"Server info: {info}")
    
    # Capture screenshot
    print("Capturing screenshot...")
    success, image_data, error, dimensions = client.capture_screen()
    if success:
        print(f"Screenshot captured: {dimensions[0]}x{dimensions[1]}")
        
        # Save screenshot
        with open("screenshot.png", "wb") as f:
            f.write(image_data)
        print("Screenshot saved as screenshot.png")
    else:
        print(f"Screenshot failed: {error}")
    
    # Example mouse click
    print("Sending mouse click...")
    if client.send_mouse_click(100, 100):
        print("Mouse click sent successfully")
    
    # Example keyboard input
    print("Sending text...")
    if client.send_text("Hello PiKVM!"):
        print("Text sent successfully")
    
    # Example key combination
    print("Sending key combination...")
    if client.send_key_combination(["Ctrl", "Alt", "t"]):
        print("Key combination sent successfully")


if __name__ == "__main__":
    main()
