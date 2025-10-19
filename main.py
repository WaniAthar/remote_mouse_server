from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pynput.mouse import Controller, Button
import json
import logging
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI()
active_controller = None
mouse = Controller()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global active_controller
    
    # Reject multiple connections
    if active_controller is not None:
        await websocket.close(
            code=4001, reason="Another user is already controlling the mouse"
        )
        return
    
    await websocket.accept()
    active_controller = websocket
    logger.info("Controller connected")
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            action = message.get("action")
            value = message.get("value", {})
            
            if action == "click":
                button_name = value.get("button", "left")
                button = Button.left if button_name == "left" else Button.right
                mouse.click(button)

            elif action == "left_press":
                mouse.press(Button.left)

            elif action == "left_release":
                mouse.release((Button.left))
            elif action == "right_press":
                mouse.press(Button.right)

            elif action == "right_press":
                mouse.release((Button.right))
            
            elif action == "scroll":
                amount = value.get("amount", 0)
                # pynput scroll: positive = up, negative = down
                mouse.scroll(0, amount)
                logger.info(f"Scroll: {amount}")
                
            elif action == "hscroll":
                amount = value.get("amount", 0)
                # Horizontal scroll: dx, dy parameters
                mouse.scroll(amount, 0)
                logger.info(f"Horizontal scroll: {amount}")
                
            elif action == "move":
                dx, dy = value.get("dx", 0), value.get("dy", 0)
                current_pos = mouse.position
                mouse.position = (current_pos[0] + dx, current_pos[1] + dy)
                # Reduced logging to avoid spam
                if abs(dx) > 1 or abs(dy) > 1:
                    logger.debug(f"Move: dx={dx:.1f}, dy={dy:.1f}")
                
                    
    except WebSocketDisconnect:
        logger.info("Controller disconnected")
    finally:
        active_controller = None
        logger.info("Mouse control released")