"""
MCP Server modifications to support PiKVM API instead of VNC

Key changes needed in the server.py file:
1. Update tool function signatures to match PiKVM client methods
2. Fix parameter mapping between MCP tools and PiKVM API
3. Handle coordinate scaling properly
4. Map VNC key codes to PiKVM key names
"""

# In the server.py file, here are the key modifications needed:

# 1. UPDATE MOUSE CLICK FUNCTION
@server.call_tool()
async def remote_macos_mouse_click(arguments: dict) -> list[TextContent]:
    """Handle mouse click with PiKVM API compatibility."""
    try:
        # Extract coordinates and scale them properly
        x = int(arguments.get("x", 0))
        y = int(arguments.get("y", 0))
        button = int(arguments.get("button", 1))
        source_width = int(arguments.get("source_width", 1366))
        source_height = int(arguments.get("source_height", 768))
        
        # Get actual screen dimensions from last screenshot
        # For PiKVM, we might need to get current dimensions
        success, screen_data, error, dimensions = await capture_vnc_screen(
            host=HOST, port=PORT, password=PASSWORD, username=USERNAME
        )
        
        if success and dimensions:
            target_width, target_height = dimensions
            
            # Scale coordinates from source to target dimensions
            scaled_x = int(x * target_width / source_width)
            scaled_y = int(y * target_height / source_height)
        else:
            # Fallback to original coordinates
            scaled_x, scaled_y = x, y
        
        # Create VNC client for mouse action
        vnc = VNCClient(host=HOST, port=PORT, password=PASSWORD, username=USERNAME)
        
        # Test connection
        success, error = vnc.connect()
        if not success:
            return [TextContent(type="text", text=f"Failed to connect: {error}")]
        
        # Map button numbers to PiKVM button names
        button_map = {1: "left", 2: "middle", 3: "right"}
        button_name = button_map.get(button, "left")
        
        # Send mouse click using PiKVM API
        success = vnc.send_mouse_click(scaled_x, scaled_y, button=button_name)
        
        vnc.close()
        
        if success:
            return [TextContent(type="text", text=f"Mouse click (button {button}) from source ({x}, {y}) to target ({scaled_x}, {scaled_y}) succeeded\nSource dimensions: {source_width}x{source_height}\nTarget dimensions: {target_width}x{target_height}\nScale factors: {target_width/source_width:.4f}x, {target_height/source_height:.4f}y")]
        else:
            return [TextContent(type="text", text=f"Mouse click failed")]
            
    except Exception as e:
        return [TextContent(type="text", text=f"Error during mouse click: {str(e)}")]


# 2. UPDATE DOUBLE CLICK FUNCTION
@server.call_tool()
async def remote_macos_mouse_double_click(arguments: dict) -> list[TextContent]:
    """Handle mouse double-click with PiKVM API compatibility."""
    try:
        x = int(arguments.get("x", 0))
        y = int(arguments.get("y", 0))
        button = int(arguments.get("button", 1))
        source_width = int(arguments.get("source_width", 1366))
        source_height = int(arguments.get("source_height", 768))
        
        # Get screen dimensions and scale coordinates (same as single click)
        success, screen_data, error, dimensions = await capture_vnc_screen(
            host=HOST, port=PORT, password=PASSWORD, username=USERNAME
        )
        
        if success and dimensions:
            target_width, target_height = dimensions
            scaled_x = int(x * target_width / source_width)
            scaled_y = int(y * target_height / source_height)
        else:
            scaled_x, scaled_y = x, y
            target_width, target_height = source_width, source_height
        
        vnc = VNCClient(host=HOST, port=PORT, password=PASSWORD, username=USERNAME)
        
        success, error = vnc.connect()
        if not success:
            return [TextContent(type="text", text=f"Failed to connect: {error}")]
        
        button_map = {1: "left", 2: "middle", 3: "right"}
        button_name = button_map.get(button, "left")
        
        # Send double-click using PiKVM API
        success = vnc.send_mouse_click(scaled_x, scaled_y, button=button_name, double_click=True)
        
        vnc.close()
        
        if success:
            return [TextContent(type="text", text=f"Mouse double-click (button {button}) from source ({x}, {y}) to target ({scaled_x}, {scaled_y}) succeeded\nSource dimensions: {source_width}x{source_height}\nTarget dimensions: {target_width}x{target_height}\nScale factors: {target_width/source_width:.4f}x, {target_height/source_height:.4f}y")]
        else:
            return [TextContent(type="text", text=f"Mouse double-click failed")]
            
    except Exception as e:
        return [TextContent(type="text", text=f"Error during mouse double-click: {str(e)}")]


# 3. UPDATE MOUSE SCROLL FUNCTION
@server.call_tool()
async def remote_macos_mouse_scroll(arguments: dict) -> list[TextContent]:
    """Handle mouse scroll with PiKVM API compatibility."""
    try:
        x = int(arguments.get("x", 0))
        y = int(arguments.get("y", 0))
        direction = arguments.get("direction", "down")
        source_width = int(arguments.get("source_width", 1366))
        source_height = int(arguments.get("source_height", 768))
        
        # Scale coordinates
        success, screen_data, error, dimensions = await capture_vnc_screen(
            host=HOST, port=PORT, password=PASSWORD, username=USERNAME
        )
        
        if success and dimensions:
            target_width, target_height = dimensions
            scaled_x = int(x * target_width / source_width)
            scaled_y = int(y * target_height / source_height)
        else:
            scaled_x, scaled_y = x, y
            target_width, target_height = source_width, source_height
        
        vnc = VNCClient(host=HOST, port=PORT, password=PASSWORD, username=USERNAME)
        
        success, error = vnc.connect()
        if not success:
            return [TextContent(type="text", text=f"Failed to connect: {error}")]
        
        # Send scroll using PiKVM API
        success = vnc.send_mouse_scroll(scaled_x, scaled_y, direction)
        
        vnc.close()
        
        if success:
            return [TextContent(type="text", text=f"Mouse scroll {direction} at ({scaled_x}, {scaled_y}) succeeded")]
        else:
            return [TextContent(type="text", text=f"Mouse scroll failed")]
            
    except Exception as e:
        return [TextContent(type="text", text=f"Error during mouse scroll: {str(e)}")]


# 4. UPDATE SEND KEYS FUNCTION - MOST IMPORTANT FIX
@server.call_tool()
async def remote_macos_send_keys(arguments: dict) -> list[TextContent]:
    """Handle keyboard input with PiKVM API compatibility."""
    try:
        vnc = VNCClient(host=HOST, port=PORT, password=PASSWORD, username=USERNAME)
        
        success, error = vnc.connect()
        if not success:
            return [TextContent(type="text", text=f"Failed to connect: {error}")]
        
        # Handle different types of keyboard input
        if "text" in arguments:
            # Send text string
            text = arguments["text"]
            success = vnc.send_text(text)
            result_msg = f"Sent text: '{text}'" if success else f"Failed to send text: '{text}'"
            
        elif "key_combination" in arguments:
            # Send key combination (e.g., "ctrl+c")
            key_combo = arguments["key_combination"]
            keys = [k.strip().title() for k in key_combo.split("+")]
            success = vnc.send_key_combination(keys)
            result_msg = f"Sent key combination: {key_combo}" if success else f"Failed to send key combination: {key_combo}"
            
        elif "special_key" in arguments:
            # Send special key (e.g., "enter", "backspace")
            special_key = arguments["special_key"]
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
                "pagedown": "Page_Down"
            }
            
            key_name = key_map.get(special_key.lower(), special_key)
            success = vnc.send_key_press(key_name)
            result_msg = f"Sent special key: {special_key}" if success else f"Failed to send special key: {special_key}"
            
        else:
            vnc.close()
            return [TextContent(type="text", text="No valid key input provided")]
        
        vnc.close()
        return [TextContent(type="text", text=result_msg)]
        
    except Exception as e:
        return [TextContent(type="text", text=f"Error during keyboard input: {str(e)}")]


# 5. UPDATE MOUSE MOVE FUNCTION
@server.call_tool()
async def remote_macos_mouse_move(arguments: dict) -> list[TextContent]:
    """Handle mouse movement with PiKVM API compatibility."""
    try:
        x = int(arguments.get("x", 0))
        y = int(arguments.get("y", 0))
        source_width = int(arguments.get("source_width", 1366))
        source_height = int(arguments.get("source_height", 768))
        
        # Scale coordinates
        success, screen_data, error, dimensions = await capture_vnc_screen(
            host=HOST, port=PORT, password=PASSWORD, username=USERNAME
        )
        
        if success and dimensions:
            target_width, target_height = dimensions
            scaled_x = int(x * target_width / source_width)
            scaled_y = int(y * target_height / source_height)
        else:
            scaled_x, scaled_y = x, y
            target_width, target_height = source_width, source_height
        
        vnc = VNCClient(host=HOST, port=PORT, password=PASSWORD, username=USERNAME)
        
        success, error = vnc.connect()
        if not success:
            return [TextContent(type="text", text=f"Failed to connect: {error}")]
        
        # Send mouse move using PiKVM API
        success = vnc.send_mouse_move(scaled_x, scaled_y)
        
        vnc.close()
        
        if success:
            return [TextContent(type="text", text=f"Mouse move to ({scaled_x}, {scaled_y}) succeeded")]
        else:
            return [TextContent(type="text", text=f"Mouse move failed")]
            
    except Exception as e:
        return [TextContent(type="text", text=f"Error during mouse move: {str(e)}")]


# 6. UPDATE DRAG AND DROP FUNCTION
@server.call_tool()
async def remote_macos_mouse_drag_n_drop(arguments: dict) -> list[TextContent]:
    """Handle mouse drag and drop with PiKVM API compatibility."""
    try:
        start_x = int(arguments.get("start_x", 0))
        start_y = int(arguments.get("start_y", 0))
        end_x = int(arguments.get("end_x", 0))
        end_y = int(arguments.get("end_y", 0))
        button = int(arguments.get("button", 1))
        source_width = int(arguments.get("source_width", 1366))
        source_height = int(arguments.get("source_height", 768))
        
        # Scale coordinates
        success, screen_data, error, dimensions = await capture_vnc_screen(
            host=HOST, port=PORT, password=PASSWORD, username=USERNAME
        )
        
        if success and dimensions:
            target_width, target_height = dimensions
            scaled_start_x = int(start_x * target_width / source_width)
            scaled_start_y = int(start_y * target_height / source_height)
            scaled_end_x = int(end_x * target_width / source_width)
            scaled_end_y = int(end_y * target_height / source_height)
        else:
            scaled_start_x, scaled_start_y = start_x, start_y
            scaled_end_x, scaled_end_y = end_x, end_y
            target_width, target_height = source_width, source_height
        
        vnc = VNCClient(host=HOST, port=PORT, password=PASSWORD, username=USERNAME)
        
        success, error = vnc.connect()
        if not success:
            return [TextContent(type="text", text=f"Failed to connect: {error}")]
        
        button_map = {1: "left", 2: "middle", 3: "right"}
        button_name = button_map.get(button, "left")
        
        # Simulate drag and drop with PiKVM API
        # Move to start position
        vnc.send_mouse_move(scaled_start_x, scaled_start_y)
        # Press button
        vnc.send_mouse_event(scaled_start_x, scaled_start_y, button_name, True)
        # Move to end position while holding button
        vnc.send_mouse_move(scaled_end_x, scaled_end_y)
        # Release button
        vnc.send_mouse_event(scaled_end_x, scaled_end_y, button_name, False)
        
        vnc.close()
        
        return [TextContent(type="text", text=f"Mouse drag from ({scaled_start_x}, {scaled_start_y}) to ({scaled_end_x}, {scaled_end_y}) completed")]
        
    except Exception as e:
        return [TextContent(type="text", text=f"Error during mouse drag: {str(e)}")]


# 7. KEEP SCREENSHOT FUNCTION AS IS (already working)
# The remote_macos_get_screen function should work as-is since we've implemented
# the capture_vnc_screen function properly


# Additional helper function for the server.py:
def get_connection_params():
    """Get connection parameters from environment or defaults."""
    import os
    
    # For PiKVM, default to HTTPS port 443
    HOST = os.getenv("PIKVM_HOST", "192.168.88.138")
    PORT = int(os.getenv("PIKVM_PORT", "443"))
    USERNAME = os.getenv("PIKVM_USERNAME", "admin")
    PASSWORD = os.getenv("PIKVM_PASSWORD", "admin")
    
    return HOST, PORT, USERNAME, PASSWORD

# Update the global variables at the top of server.py:
HOST, PORT, USERNAME, PASSWORD = get_connection_params()
