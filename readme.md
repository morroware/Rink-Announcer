# Rink Announcement System

**Author:** Seth Morrow  
**Date:** March 30, 2025  
**For:** Castle Fun Center Roller Rink

## Overview

The Rink Announcement System automates announcements at the Castle Fun Center roller rink, managing session times based on color-coded wristbands. The system announces when specific color wristbands have expired, plays rules announcements, and allows for custom announcements.

## Features

- **Day-Specific Scheduling:** Different announcement schedules for each day of the week
- **Color Rotation Management:** Automatically identifies the current wristband colors from the database
- **Web Control Panel:** Easy-to-use interface for managing announcements
- **Text-to-Speech:** High-quality announcements using Microsoft Edge TTS
- **Instant Announcements:** Option to make immediate announcements
- **Custom Templates:** Create reusable announcement templates

## System Requirements

- Python 3.8+
- Microsoft SQL Server database connection
- mpg123 (for audio playback)
- Internet connection (for Edge TTS)
- systemd-compatible Linux environment

## Python Dependencies

- Flask
- edge_tts
- pymssql
- asyncio

## Setup

1. Install required dependencies:
   ```
   pip install flask edge_tts pymssql
   sudo apt-get install mpg123
   ```

2. Ensure database configuration is correct in `config.ini`

3. Set up the systemd service:
   ```
   sudo cp announcer.service /etc/systemd/system/
   sudo systemctl enable announcer.service
   sudo systemctl start announcer.service
   ```

4. Start the web interface:
   ```
   python settings.py
   ```

5. Access the control panel at http://localhost:5000

## Day Configuration

The system uses different configuration files for each day:
- `fri.ini`: Friday schedule
- `sat.ini`: Saturday schedule
- `sun.ini`: Sunday schedule
- `thurs.ini`: Thursday schedule
- `config.ini`: Default configuration

## Announcement Types

- **Hour Change:** Announces when wristband colors expire
- **Color Warning:** Gives 5-minute warnings before expiration
- **Rules:** Plays rink rules announcements
- **Advertisement:** Plays promotional announcements
- **Custom:** Create your own announcement types

## Troubleshooting

- Check `announcement_script.log` for error messages
- Verify database connection details
- Ensure the system has permission to create/modify files
- Check that mpg123 is properly installed
- Verify that the systemd service is running

## Maintenance

- Regularly check for unexpected shutdowns in the log
- Test announcements after making configuration changes
- Adjust volumes as needed for the rink environment

For assistance, contact the system administrator.
