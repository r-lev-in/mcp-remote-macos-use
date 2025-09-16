"""
Modified action handlers to work with PiKVM API client instead of VNC.

These functions replace the VNC-based implementations with PiKVM API calls
while maintaining the same interface for the MCP server.
"""

import asyncio
import logging
from typing import Optional, Tuple
from vnc_client import VNCClient, capture_vnc_screen
import os

logger = logging.getLogger(__name__)

# Get connection parameters from environment
HOST = os.getenv("PIKVM_HOST", "192.168.88.138")
PORT = int(os.getenv("PIKVM_PORT", "443"))
USERNAME = os.getenv("PIKVM_USERNAME", "admin")
PASSWORD = os.getenv("PIKVM_PASSWORD", "admin")


async def get_screen() -> Tuple[bool, Optional[bytes], Optional[str], Optional[Tuple[int, int]]]:
    """
    Capture screenshot using PiKVM API.
    
    Returns:
        Tuple of (success, image_data, error_message, dimensions)
    """
    try:
        return await capture_vnc_screen(
            host=HOST,
            port=PORT,
            password=PASSWORD,
            username=USERNAME
        )
    except Exception as e:
        logger.error(f"Screenshot capture failed: {str(e)}")
        return False, None, str(e), None


async def mouse_click(x: int, y: int, button: int = 1, source_width: Optional[int] = None, 
                     source_height: Optional[int] = None) -> Tuple[bool, str]:
    """
    Perform mouse click using PiKVM API.
    
    Args:
        x: X coordinate in source dimensions
        y: Y coordinate in source dimensions  
        button: Mouse button (1=left, 2=middle, 3=right)
        source_width: Source screen width for scaling (optional, will use current if not provided)
        source_height: Source screen height for scaling (optional, will use current if not provided)
        
    Returns:
        Tuple of (success, message)
    """
    try:
        # Create PiKVM client
        vnc = VNCClient(host=HOST, port=PORT, password=PASSWORD, username=USERNAME)
        
        # Test connection
        success, error = vnc.connect()
        if not success:
            return False, f"Failed to connect: {error}"
        
        # Get current screen dimensions
        success, screen_data, error, current_dimensions = await get_screen()
        if success and current_dimensions:
            target_width, target_height = current_dimensions
            
            # Use provided source dimensions or default to current dimensions
            src_width = source_width or target_width
            src_height = source_height or target_height
            
            # Scale coordinates
            scaled_x = int(x * target_width / src_width)
            scaled_y = int(y * target_height / src_height)
            
            # Log dimension information for debugging
            if source_width and source_height:
                logger.debug(f"Scaling from provided source {src_width}x{src_height} to target {target_width}x{target_height}")
            else:
                logger.debug(f"Using current dimensions {target_width}x{target_height} (no scaling needed)")
        else:
            # Fallback to original coordinates if screen capture fails
            scaled_x, scaled_y = x, y
            src_width = source_width or 1366  # Fallback default
            src_height = source_height or 768
            target_width, target_height = src_width, src_height
            logger.warning("Could not get current screen dimensions, using coordinates as-is")
        
        # Map button numbers to PiKVM button names
        button_map = {1: "left", 2: "middle", 3: "right"}
        button_name = button_map.get(button, "left")
        
        # Perform click
        success = vnc.send_mouse_click(scaled_x, scaled_y, button=button_name)
        
        vnc.close()
        
        if success:
            message = (f"Mouse click (button {button}) from source ({x}, {y}) to target ({scaled_x}, {scaled_y}) succeeded\n"
                      f"Source dimensions: {src_width}x{src_height}\n"
                      f"Target dimensions: {target_width}x{target_height}\n" 
                      f"Scale factors: {target_width/src_width:.4f}x, {target_height/src_height:.4f}y")
            return True, message
        else:
            return False, "Mouse click failed"
            
    except Exception as e:
        logger.error(f"Mouse click error: {str(e)}")
        return False, f"Error during mouse click: {str(e)}"


async def mouse_double_click(x: int, y: int, button: int = 1, source_width: Optional[int] = None,
                           source_height: Optional[int] = None) -> Tuple[bool, str]:
    """
    Perform mouse double-click using PiKVM API.
    
    Args:
        x: X coordinate in source dimensions
        y: Y coordinate in source dimensions
        button: Mouse button (1=left, 2=middle, 3=right)
        source_width: Source screen width for scaling (optional)
        source_height: Source screen height for scaling (optional)
        
    Returns:
        Tuple of (success, message)
    """
    try:
        vnc = VNCClient(host=HOST, port=PORT, password=PASSWORD, username=USERNAME)
        
        success, error = vnc.connect()
        if not success:
            return False, f"Failed to connect: {error}"
        
        # Get current screen dimensions and handle scaling
        success, screen_data, error, current_dimensions = await get_screen()
        if success and current_dimensions:
            target_width, target_height = current_dimensions
            src_width = source_width or target_width
            src_height = source_height or target_height
            scaled_x = int(x * target_width / src_width)
            scaled_y = int(y * target_height / src_height)
        else:
            scaled_x, scaled_y = x, y
            src_width = source_width or 1366
            src_height = source_height or 768
            target_width, target_height = src_width, src_height
        
        button_map = {1: "left", 2: "middle", 3: "right"}
        button_name = button_map.get(button, "left")
        
        # Perform double-click
        success = vnc.send_mouse_click(scaled_x, scaled_y, button=button_name, double_click=True)
        
        vnc.close()
        
        if success:
            message = (f"Mouse double-click (button {button}) from source ({x}, {y}) to target ({scaled_x}, {scaled_y}) succeeded\n"
                      f"Source dimensions: {src_width}x{src_height}\n"
                      f"Target dimensions: {target_width}x{target_height}\n"
                      f"Scale factors: {target_width/src_width:.4f}x, {target_height/src_height:.4f}y")
            return True, message
        else:
            return False, "Mouse double-click failed"
            
    except Exception as e:
        logger.error(f"Mouse double-click error: {str(e)}")
        return False, f"Error during mouse double-click: {str(e)}"


async def mouse_scroll(x: int, y: int, direction: str, source_width: Optional[int] = None,
                      source_height: Optional[int] = None) -> Tuple[bool, str]:
    """
    Perform mouse scroll using PiKVM API.
    
    Args:
        x: X coordinate in source dimensions
        y: Y coordinate in source dimensions
        direction: Scroll direction ("up" or "down")
        source_width: Source screen width for scaling (optional)
        source_height: Source screen height for scaling (optional)
        
    Returns:
        Tuple of (success, message)
    """
    try:
        vnc = VNCClient(host=HOST, port=PORT, password=PASSWORD, username=USERNAME)
        
        success, error = vnc.connect()
        if not success:
            return False, f"Failed to connect: {error}"
        
        # Scale coordinates using dynamic dimensions
        success, screen_data, error, current_dimensions = await get_screen()
        if success and current_dimensions:
            target_width, target_height = current_dimensions
            src_width = source_width or target_width
            src_height = source_height or target_height
            scaled_x = int(x * target_width / src_width)
            scaled_y = int(y * target_height / src_height)
        else:
            scaled_x, scaled_y = x, y
        
        # Perform scroll
        success = vnc.send_mouse_scroll(scaled_x, scaled_y, direction)
        
        vnc.close()
        
        if success:
            return True, f"Mouse scroll {direction} at ({scaled_x}, {scaled_y}) succeeded"
        else:
            return False, "Mouse scroll failed"
            
    except Exception as e:
        logger.error(f"Mouse scroll error: {str(e)}")
        return False, f"Error during mouse scroll: {str(e)}"


async def send_keys(text: Optional[str] = None, key_combination: Optional[str] = None,
                   special_key: Optional[str] = None) -> Tuple[bool, str]:
    """
    Send keyboard input using PiKVM API.
    
    Args:
        text: Plain text to type
        key_combination: Key combination like "ctrl+c"
        special_key: Special key like "enter", "backspace"
        
    Returns:
        Tuple of (success, message)
    """
    try:
        vnc = VNCClient(host=HOST, port=PORT, password=PASSWORD, username=USERNAME)
        
        success, error = vnc.connect()
        if not success:
            return False, f"Failed to connect: {error}"
        
        # Handle different types of keyboard input
        if text:
            # Send text string
            success = vnc.send_text(text)
            result_msg = f"Sent text: '{text}'" if success else f"Failed to send text: '{text}'"
            
        elif key_combination:
            # Send key combination (e.g., "ctrl+c")
            keys = [k.strip().title() for k in key_combination.split("+")]
            # Map common key names
            key_map = {
                "Ctrl": "Control_L",
                "Alt": "Alt_L", 
                "Shift": "Shift_L",
                "Cmd": "Super_L",
                "Super": "Super_L"
            }
            mapped_keys = [key_map.get(k, k) for k in keys]
            
            success = vnc.send_key_combination(mapped_keys)
            result_msg = f"Sent key combination: {key_combination}" if success else f"Failed to send key combination: {key_combination}"
            
        elif special_key:
            # Send special key
            # Map common special keys to PiKVM key names
            key_map = {
                "enter": "Return",
                "return": "Return",
                "backspace": "BackSpace", 
                "delete": "Delete",
                "tab": "Tab",
                "escape": "Escape",
                "space": "space",
                "up": "Up",
                "down": "Down", 
                "left": "Left",
                "right": "Right",
                "home": "Home",
                "end": "End",
                "pageup": "Page_Up",
                "pagedown": "Page_Down",
                "f1": "F1", "f2": "F2", "f3": "F3", "f4": "F4",
                "f5": "F5", "f6": "F6", "f7": "F7", "f8": "F8",
                "f9": "F9", "f10": "F10", "f11": "F11", "f12": "F12"
            }
            
            key_name = key_map.get(special_key.lower(), special_key)
            success = vnc.send_key_press(key_name)
            result_msg = f"Sent special key: {special_key}" if success else f"Failed to send special key: {special_key}"
            
        else:
            vnc.close()
            return False, "No valid key input provided"
        
        vnc.close()
        return success, result_msg
        
    except Exception as e:
        logger.error(f"Keyboard input error: {str(e)}")
        return False, f"Error during keyboard input: {str(e)}"


async def mouse_move(x: int, y: int, source_width: Optional[int] = None,
                    source_height: Optional[int] = None) -> Tuple[bool, str]:
    """
    Move mouse cursor using PiKVM API.
    
    Args:
        x: X coordinate in source dimensions
        y: Y coordinate in source dimensions
        source_width: Source screen width for scaling (optional)
        source_height: Source screen height for scaling (optional)
        
    Returns:
        Tuple of (success, message)
    """
    try:
        vnc = VNCClient(host=HOST, port=PORT, password=PASSWORD, username=USERNAME)
        
        success, error = vnc.connect()
        if not success:
            return False, f"Failed to connect: {error}"
        
        # Scale coordinates using dynamic dimensions
        success, screen_data, error, current_dimensions = await get_screen()
        if success and current_dimensions:
            target_width, target_height = current_dimensions
            src_width = source_width or target_width
            src_height = source_height or target_height
            scaled_x = int(x * target_width / src_width)
            scaled_y = int(y * target_height / src_height)
        else:
            scaled_x, scaled_y = x, y
        
        # Move mouse
        success = vnc.send_mouse_move(scaled_x, scaled_y)
        
        vnc.close()
        
        if success:
            return True, f"Mouse move to ({scaled_x}, {scaled_y}) succeeded"
        else:
            return False, "Mouse move failed"
            
    except Exception as e:
        logger.error(f"Mouse move error: {str(e)}")
        return False, f"Error during mouse move: {str(e)}"


async def mouse_drag_drop(start_x: int, start_y: int, end_x: int, end_y: int,
                         button: int = 1, source_width: Optional[int] = None,
                         source_height: Optional[int] = None) -> Tuple[bool, str]:
    """
    Perform mouse drag and drop using PiKVM API.
    
    Args:
        start_x: Start X coordinate in source dimensions
        start_y: Start Y coordinate in source dimensions
        end_x: End X coordinate in source dimensions
        end_y: End Y coordinate in source dimensions
        button: Mouse button (1=left, 2=middle, 3=right)
        source_width: Source screen width for scaling (optional)
        source_height: Source screen height for scaling (optional)
        
    Returns:
        Tuple of (success, message)
    """
    try:
        vnc = VNCClient(host=HOST, port=PORT, password=PASSWORD, username=USERNAME)
        
        success, error = vnc.connect()
        if not success:
            return False, f"Failed to connect: {error}"
        
        # Scale coordinates using dynamic dimensions
        success, screen_data, error, current_dimensions = await get_screen()
        if success and current_dimensions:
            target_width, target_height = current_dimensions
            src_width = source_width or target_width
            src_height = source_height or target_height
            scaled_start_x = int(start_x * target_width / src_width)
            scaled_start_y = int(start_y * target_height / src_height)
            scaled_end_x = int(end_x * target_width / src_width)
            scaled_end_y = int(end_y * target_height / src_height)
        else:
            scaled_start_x, scaled_start_y = start_x, start_y
            scaled_end_x, scaled_end_y = end_x, end_y
        
        button_map = {1: "left", 2: "middle", 3: "right"}
        button_name = button_map.get(button, "left")
        
        # Simulate drag and drop
        # Move to start position
        vnc.send_mouse_move(scaled_start_x, scaled_start_y)
        # Press button
        vnc.send_mouse_event(scaled_start_x, scaled_start_y, button_name, True)
        # Move to end position while holding button
        vnc.send_mouse_move(scaled_end_x, scaled_end_y)
        # Release button
        vnc.send_mouse_event(scaled_end_x, scaled_end_y, button_name, False)
        
        vnc.close()
        
        return True, f"Mouse drag from ({scaled_start_x}, {scaled_start_y}) to ({scaled_end_x}, {scaled_end_y}) completed"
        
    except Exception as e:
        logger.error(f"Mouse drag error: {str(e)}")
        return False, f"Error during mouse drag: {str(e)}"


# Additional utility functions for PiKVM integration

async def reset_hid() -> Tuple[bool, str]:
    """
    Reset HID devices (keyboard/mouse) using PiKVM API.
    
    Returns:
        Tuple of (success, message)
    """
    try:
        vnc = VNCClient(host=HOST, port=PORT, password=PASSWORD, username=USERNAME)
        
        success, error = vnc.connect()
        if not success:
            return False, f"Failed to connect: {error}"
        
        success = vnc.reset_hid()
        vnc.close()
        
        if success:
            return True, "HID devices reset successfully"
        else:
            return False, "HID reset failed"
            
    except Exception as e:
        logger.error(f"HID reset error: {str(e)}")
        return False, f"Error during HID reset: {str(e)}"


async def get_server_info() -> Tuple[bool, str, Optional[dict]]:
    """
    Get PiKVM server information.
    
    Returns:
        Tuple of (success, message, info_dict)
    """
    try:
        vnc = VNCClient(host=HOST, port=PORT, password=PASSWORD, username=USERNAME)
        
        success, error = vnc.connect()
        if not success:
            return False, f"Failed to connect: {error}", None
        
        info = vnc.get_server_info()
        vnc.close()
        
        if info:
            return True, "Server info retrieved", info
        else:
            return False, "Failed to get server info", None
            
    except Exception as e:
        logger.error(f"Server info error: {str(e)}")
        return False, f"Error getting server info: {str(e)}", None


# Function mapping for backwards compatibility
FUNCTION_MAP = {
    "get_screen": get_screen,
    "mouse_click": mouse_click,
    "mouse_double_click": mouse_double_click, 
    "mouse_scroll": mouse_scroll,
    "send_keys": send_keys,
    "mouse_move": mouse_move,
    "mouse_drag_drop": mouse_drag_drop,
    "reset_hid": reset_hid,
    "get_server_info": get_server_info
}
