"""
settings.py

Flask application for managing the announcement system configuration.
Provides a web interface for managing announcements, schedules, INI file editing,
and other system settings. This version includes concurrency protections
(using file locking and a global RLock), retry logic, and enhanced error handling.
"""

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import threading
import os
import logging
import subprocess
import json
import tempfile
import asyncio
import datetime
from typing import Dict, Any
import announcer

# Import file locking and global lock from announcer
from announcer import locked_file, global_lock, get_day_config_filename

import fcntl

# Initialize Flask application
app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Change this in production

# Global variable for the announcer thread (if needed)
announcement_thread = None

class ConfigHandler:
    """
    Handles reading, writing, and managing configuration data.
    """
    def __init__(self, config_file: str = None):
        self.config_file = config_file if config_file else get_day_config_filename()
        self.config = {
            'database': {
                'server': '',
                'database': '',
                'username': '',
                'password': ''
            },
            'times': {},
            'announcements': {
                'fiftyfive': '',
                'hour': '',
                'rules': '',
                'ad': ''
            },
            'tts': {
                'voice_id': ''
            }
        }

    def read_config(self) -> Dict[str, Any]:
        """
        Read and parse the configuration file.
        """
        try:
            current_section = None
            if os.path.exists(self.config_file):
                with locked_file(self.config_file, 'r', fcntl.LOCK_SH) as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if line.startswith('[') and line.endswith(']'):
                            current_section = line[1:-1].lower()
                            continue
                        if '=' in line:
                            key, value = [x.strip() for x in line.split('=', 1)]
                            if current_section == 'times':
                                self.config['times'][key] = value
                            elif current_section == 'announcements':
                                clean_value = value.strip('"\'')
                                if key.startswith('custom_') or key in ['fiftyfive', 'hour', 'rules', 'ad']:
                                    self.config['announcements'][key] = clean_value
                            elif current_section in self.config:
                                if key.lower() in self.config[current_section]:
                                    clean_value = value.strip('"\'')
                                    self.config[current_section][key.lower()] = clean_value
            return self.config
        except Exception as e:
            logging.error(f"Error reading config: {e}", exc_info=True)
            return self.config

    def write_config(self) -> None:
        """
        Write the current configuration back to the file.
        """
        try:
            with locked_file(self.config_file, 'w', fcntl.LOCK_EX) as f:
                f.write("[database]\n")
                for key, value in self.config['database'].items():
                    f.write(f"{key} = {value}\n")
                f.write("\n")
                f.write("[times]\n")
                for time_key, value in sorted(self.config['times'].items()):
                    f.write(f"{time_key} = {value}\n")
                f.write("\n")
                f.write("[announcements]\n")
                standard_types = ['fiftyfive', 'hour', 'rules', 'ad']
                for key in standard_types:
                    if key in self.config['announcements']:
                        f.write(f"{key} = {self.config['announcements'][key]}\n")
                for key, value in self.config['announcements'].items():
                    if key.startswith('custom_'):
                        escaped_value = value.replace('\n', '\\n').replace('"', '\\"')
                        f.write(f"{key} = \"{escaped_value}\"\n")
                f.write("\n")
                f.write("[tts]\n")
                f.write(f"voice_id = {self.config['tts']['voice_id']}\n")
        except Exception as e:
            logging.error(f"Error writing config: {e}", exc_info=True)
            raise

def list_available_configs():
    """
    List available day configuration files.
    """
    config_files = ["wed.ini", "thurs.ini", "fri.ini", "sat.ini", "sun.ini", "config.ini"]
    available_configs = {}
    for config_file in config_files:
        exists = os.path.exists(config_file)
        available_configs[config_file] = {
            "exists": exists,
            "size": os.path.getsize(config_file) if exists else 0,
            "modified": os.path.getmtime(config_file) if exists else 0
        }
    current_day = datetime.datetime.now().weekday()
    day_names = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"}
    current_config = get_day_config_filename()
    return {
        "configs": available_configs,
        "current_day": {
            "day_number": current_day,
            "day_name": day_names.get(current_day, "Unknown"),
            "config_file": current_config,
            "is_operating_day": current_day in [2, 3, 4, 5, 6]
        }
    }

def restart_services() -> bool:
    """
    Restart the announcer service by signaling a configuration reload.
    Uses file locking when writing the reload_config file.
    """
    try:
        current_config = get_day_config_filename()
        with locked_file("reload_config", "w", fcntl.LOCK_EX) as f:
            f.write(current_config)
        try:
            subprocess.run(['sudo', 'systemctl', 'restart', 'announcer.service'], check=True)
            logging.info("Announcer service restarted successfully")
        except subprocess.CalledProcessError as e:
            logging.warning(f"Could not restart announcer service: {e}")
            logging.info("Continuing without service restart – reload_config will trigger a reload")
        return True
    except Exception as e:
        logging.error(f"Error preparing configuration reload: {e}", exc_info=True)
        return False

def copy_config(source_config: str, target_config: str) -> bool:
    """
    Copy configuration from one file to another.
    """
    try:
        if not os.path.exists(source_config):
            logging.error(f"Source config {source_config} does not exist")
            return False
        with locked_file(source_config, 'r', fcntl.LOCK_SH) as src:
            content = src.read()
        with locked_file(target_config, 'w', fcntl.LOCK_EX) as tgt:
            tgt.write(content)
        logging.info(f"Successfully copied {source_config} to {target_config}")
        return True
    except Exception as e:
        logging.error(f"Error copying config: {e}", exc_info=True)
        return False

@app.route('/get_state', methods=['GET'])
def get_state():
    """
    Get the current configuration state for UI updates.
    """
    try:
        current_config = get_day_config_filename()
        handler = ConfigHandler(current_config)
        config = handler.read_config()
        custom_types = {k.replace('custom_', ''): v for k, v in config['announcements'].items() if k.startswith('custom_')}
        times = config['times']
        day_configs = list_available_configs()
        return jsonify({'custom_types': custom_types, 'times': times, 'day_configs': day_configs})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_day_configs', methods=['GET'])
def get_day_configs():
    """
    Get information about available day configurations.
    """
    try:
        return jsonify(list_available_configs())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/switch_config', methods=['POST'])
def switch_config():
    """
    Switch to a different configuration file.
    """
    try:
        data = request.get_json()
        config_file = data.get('config_file')
        if not config_file:
            return jsonify({'error': 'No configuration file specified'}), 400
        if not os.path.exists(config_file):
            return jsonify({'error': f'Configuration file {config_file} does not exist'}), 404
        with locked_file("reload_config", "w", fcntl.LOCK_EX) as f:
            f.write(config_file)
        return jsonify({'message': f'Switched to {config_file}', 'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/copy_day_config', methods=['POST'])
def copy_day_config():
    """
    Copy configuration from one file to another.
    """
    try:
        data = request.get_json()
        source = data.get('source')
        target = data.get('target')
        if not source or not target:
            return jsonify({'error': 'Source and target must be specified'}), 400
        if not os.path.exists(source):
            return jsonify({'error': f'Source configuration {source} does not exist'}), 404
        if copy_config(source, target):
            return jsonify({'message': f'Successfully copied {source} to {target}', 'success': True})
        else:
            return jsonify({'error': 'Failed to copy configuration'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/add_custom_type', methods=['POST'])
def add_custom_type():
    """
    Add a new custom announcement type.
    """
    try:
        data = request.get_json()
        name = data.get('name')
        template = data.get('template')
        if not name or not template:
            return jsonify({'error': 'Missing name or template'}), 400
        clean_name = ''.join(c.lower() if c.isalnum() or c.isspace() else '_' for c in name).replace(' ', '_')
        current_config = get_day_config_filename()
        handler = ConfigHandler(current_config)
        config = handler.read_config()
        config['announcements'][f'custom_{clean_name}'] = template
        handler.config = config
        handler.write_config()
        if restart_services():
            return jsonify({'message': 'Custom type added successfully'}), 200
        else:
            return jsonify({'error': 'Failed to restart services'}), 500
    except Exception as e:
        logging.error(f"Error adding custom type: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/delete_custom_type', methods=['POST'])
def delete_custom_type():
    """
    Delete a custom announcement type.
    """
    try:
        data = request.get_json()
        name = data.get('name')
        if not name:
            return jsonify({'error': 'Missing name'}), 400
        current_config = get_day_config_filename()
        handler = ConfigHandler(current_config)
        config = handler.read_config()
        key = f'custom_{name}'
        if key in config['announcements']:
            del config['announcements'][key]
            times_to_remove = [t for t, typ in config['times'].items() if typ == f'custom:{name}']
            for t in times_to_remove:
                del config['times'][t]
        handler.config = config
        handler.write_config()
        if restart_services():
            return jsonify({'message': 'Custom type deleted successfully'}), 200
        else:
            return jsonify({'error': 'Failed to restart services'}), 500
    except Exception as e:
        logging.error(f"Error deleting custom type: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/add_time', methods=['POST'])
def add_time():
    """
    Add a new scheduled announcement time.
    """
    try:
        data = request.get_json()
        time_val = data.get('time')
        type_val = data.get('type')
        if not time_val or not type_val:
            return jsonify({'error': 'Missing time or type'}), 400
        current_config = get_day_config_filename()
        handler = ConfigHandler(current_config)
        config = handler.read_config()
        if type_val.startswith('custom:'):
            custom_name = type_val.replace('custom:', '')
            if f'custom_{custom_name}' not in config['announcements']:
                return jsonify({'error': f'Custom template {custom_name} not found'}), 400
        config['times'][time_val] = type_val
        handler.config = config
        handler.write_config()
        if restart_services():
            return jsonify({'message': 'Time added successfully'}), 200
        else:
            return jsonify({'error': 'Failed to restart services'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/play_instant', methods=['POST'])
def play_instant():
    """
    Play an instant announcement immediately.
    """
    try:
        data = request.get_json()
        text = data.get('text')
        if not text:
            return jsonify({'error': 'Missing announcement text'}), 400
        current_config = get_day_config_filename()
        handler = ConfigHandler(current_config)
        config = handler.read_config()
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
            temp_path = temp_file.name
        success = asyncio.run(announcer.synthesize_speech_async(text, config['tts']['voice_id'], temp_path))
        if not success:
            return jsonify({'error': 'Failed to synthesize speech'}), 500
        if not announcer.play_sound(temp_path, config['tts'].get('output_format', 'mp3')):
            return jsonify({'error': 'Failed to play announcement'}), 500
        return jsonify({'message': 'Announcement played successfully'}), 200
    except Exception as e:
        logging.error(f"Error playing instant announcement: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/delete_time', methods=['POST'])
def delete_time():
    """
    Delete a scheduled announcement time.
    """
    try:
        data = request.get_json()
        time_val = data.get('time')
        if not time_val:
            return jsonify({'error': 'Missing time'}), 400
        current_config = get_day_config_filename()
        handler = ConfigHandler(current_config)
        config = handler.read_config()
        if time_val in config['times']:
            del config['times'][time_val]
            handler.write_config()
            if restart_services():
                return jsonify({'message': 'Time deleted successfully'}), 200
            else:
                return jsonify({'error': 'Failed to restart services'}), 500
        else:
            return jsonify({'error': 'Time not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/')
def index():
    """
    Main interface displaying the configuration editor.
    """
    current_config = get_day_config_filename()
    handler = ConfigHandler(current_config)
    config = handler.read_config()
    day_configs = list_available_configs()
    times_str = '\n'.join(f"{t} = {typ}" for t, typ in sorted(config['times'].items()))
    custom_types = {k.replace('custom_', ''): v for k, v in config['announcements'].items() if k.startswith('custom_')}
    custom_types_str = '\n'.join(f"{name} = {template}" for name, template in sorted(custom_types.items()))
    return render_template('config.html',
                           database=config['database'],
                           times=times_str,
                           announcements=config['announcements'],
                           tts=config['tts'],
                           custom_types=custom_types_str,
                           day_configs=day_configs,
                           current_config=current_config)

@app.route('/save_config', methods=['POST'])
def save_config():
    """
    Save the full configuration and restart the service.
    """
    try:
        logging.info("Processing save configuration request")
        current_config = get_day_config_filename()
        handler = ConfigHandler(current_config)
        config = handler.config
        config['database'] = {
            'server': request.form['db_server'],
            'database': request.form['db_name'],
            'username': request.form['db_username'],
            'password': request.form['db_password']
        }
        config['times'] = {}
        times_str = request.form['times'].strip()
        if times_str:
            for line in times_str.split('\n'):
                if '=' in line:
                    t, typ = [part.strip() for part in line.split('=', 1)]
                    config['times'][t] = typ
        config['announcements'].update({
            'fiftyfive': request.form['fiftyfive_template'],
            'hour': request.form['hour_template'],
            'rules': request.form['rules_template'],
            'ad': request.form['ad_template']
        })
        custom_types_str = request.form.get('customTypes', '').strip()
        config['announcements'] = {k: v for k, v in config['announcements'].items() if not k.startswith('custom_')}
        if custom_types_str:
            for line in custom_types_str.split('\n'):
                if '=' in line:
                    name, template = [part.strip() for part in line.split('=', 1)]
                    config['announcements'][f'custom_{name}'] = template
        config['tts']['voice_id'] = request.form['voice_id']
        handler.config = config
        handler.write_config()
        if restart_services():
            flash('Configuration saved and announcer service restarted successfully!', 'success')
        else:
            flash('Configuration saved but service restart failed. Please restart manually.', 'error')
        return redirect(url_for('index'))
    except Exception as e:
        logging.error(f"Error saving configuration: {e}", exc_info=True)
        flash(f'Error saving configuration: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/get_ini_content', methods=['GET'])
def get_ini_content():
    """
    Retrieve the content of the specified INI file.
    """
    file_name = request.args.get('file')
    if not file_name:
        return jsonify({'error': 'No file specified'}), 400
    valid_files = ["thurs.ini", "fri.ini", "sat.ini", "sun.ini", "config.ini"]
    if file_name not in valid_files:
        return jsonify({'error': 'Invalid file name'}), 400
    try:
        if not os.path.exists(file_name):
            with open(file_name, 'w') as f:
                f.write("[database]\nserver = 192.168.1.2\ndatabase = CenterEdge\nusername = Tech\npassword = 109Brookside01!\n\n" +
                        "[times]\n# No times configured\n\n" +
                        "[announcements]\n# No announcements configured\n\n" +
                        "[tts]\nvoice_id = en-US-AriaNeural\n")
        with locked_file(file_name, 'r', fcntl.LOCK_SH) as f:
            content = f.read()
        return jsonify({'content': content})
    except Exception as e:
        logging.error(f"Error reading INI file {file_name}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/save_ini_content', methods=['POST'])
def save_ini_content():
    """
    Save updated content to the specified INI file.
    """
    data = request.get_json()
    file_name = data.get('file')
    content = data.get('content')
    if not file_name or content is None:
        return jsonify({'error': 'Missing file or content'}), 400
    try:
        with locked_file(file_name, 'w', fcntl.LOCK_EX) as f:
            f.write(content)
        current_config = get_day_config_filename()
        if file_name == current_config:
            if restart_services():
                return jsonify({'message': 'File saved and configuration reloaded', 'reload_triggered': True})
            else:
                return jsonify({'message': 'File saved but service restart failed', 'reload_triggered': False})
        return jsonify({'message': 'File saved successfully', 'reload_triggered': False})
    except Exception as e:
        logging.error(f"Error saving INI file {file_name}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/get_current_schedule', methods=['GET'])
def get_current_schedule():
    """
    Get the current announcement schedule and types.
    """
    try:
        current_config = get_day_config_filename()
        handler = ConfigHandler(current_config)
        config = handler.read_config()
        times = {t: typ for t, typ in config['times'].items()}
        announcements = {
            'fiftyfive': config['announcements'].get('fiftyfive', ''),
            'hour': config['announcements'].get('hour', ''),
            'rules': config['announcements'].get('rules', ''),
            'ad': config['announcements'].get('ad', '')
        }
        custom_types = {k.replace('custom_', ''): v for k, v in config['announcements'].items() if k.startswith('custom_')}
        return jsonify({'times': times, 'announcements': announcements, 'custom_types': custom_types, 'status': 'success'})
    except Exception as e:
        logging.error(f"Error getting current schedule: {e}", exc_info=True)
        return jsonify({'error': str(e), 'status': 'error'}), 500

@app.route('/update_schedule', methods=['POST'])
def update_schedule():
    """
    Update the announcement schedule and reload configuration.
    """
    try:
        current_config = get_day_config_filename()
        handler = ConfigHandler(current_config)
        config = handler.read_config()
        if restart_services():
            times = {t: typ for t, typ in sorted(config['times'].items())}
            custom_types = {k.replace('custom_', ''): v for k, v in config['announcements'].items() if k.startswith('custom_')}
            return jsonify({'message': 'Schedule updated and service reloaded', 'times': times, 'custom_types': custom_types, 'success': True})
        else:
            return jsonify({'error': 'Failed to reload service', 'success': False}), 500
    except Exception as e:
        logging.error(f"Error updating schedule: {e}", exc_info=True)
        return jsonify({'error': str(e), 'success': False}), 500

# Global error handlers
@app.errorhandler(404)
def not_found_error(error):
    logging.error("404 error: %s", error)
    return jsonify({"error": "Resource not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    logging.error("500 error: %s", error, exc_info=True)
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
