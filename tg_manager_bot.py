"""
Backward-compatibility alias for levitor_bot.py.
Allows existing hosting panels and container startup scripts configured with 'tg_manager_bot.py' to run seamlessly.
"""
from levitor_bot import *

if __name__ == "__main__":
    main()
