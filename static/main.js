/**
 * main.js
 * 
 * JavaScript code for the Rink Announcement System configuration interface.
 * This file handles UI interactions including sidebar behavior, tab switching,
 * INI file editing, schedule management, custom types, instant announcements, 
 * and refreshing state from the server.
 * 
 * Author: [Your Name]
 * Date: [Current Date]
 */

/* ============================
   Utility Functions
============================ */

/**
 * Utility object containing helper functions.
 */
const Utils = {
    /**
     * Format a time string (HH:MM) into 12-hour format with AM/PM.
     * @param {string} time - The time in HH:MM format.
     * @returns {string} The formatted time.
     */
    formatTime: function(time) {
        const [hours, minutes] = time.split(':').map(Number);
        const period = hours >= 12 ? 'PM' : 'AM';
        const displayHours = hours % 12 || 12;
        return `${displayHours}:${minutes.toString().padStart(2, '0')} ${period}`;
    },

    /**
     * Format a number of minutes into a display string.
     * @param {number} minutes - Number of minutes.
     * @returns {string} Formatted minute string.
     */
    formatMinutes: function(minutes) {
        return `${minutes} minute${minutes !== 1 ? 's' : ''}`;
    },

    /**
     * Display a notification message in the UI.
     * @param {string} message - The message to display.
     * @param {string} type - The type of notification ('success', 'error', 'warning', or 'info').
     */
    showNotification: function(message, type = 'info') {
        const flashContainer = document.querySelector('.flash-container');
        if (!flashContainer) return;

        const alertHtml = `
            <div class="alert alert-${type}">
                <i class="fa-solid ${this.getIconForType(type)}"></i>
                ${message}
                <button class="alert-close">
                    <i class="fa-solid fa-xmark"></i>
                </button>
            </div>
        `;
        flashContainer.insertAdjacentHTML('beforeend', alertHtml);

        const newAlert = flashContainer.lastElementChild;
        newAlert.querySelector('.alert-close').addEventListener('click', function() {
            newAlert.remove();
        });

        // Auto dismiss the alert after 5 seconds
        setTimeout(() => {
            newAlert.style.opacity = '0';
            setTimeout(() => {
                newAlert.remove();
            }, 300);
        }, 5000);
    },

    /**
     * Get the icon class for a given notification type.
     * @param {string} type - The notification type.
     * @returns {string} The icon class.
     */
    getIconForType: function(type) {
        switch(type) {
            case 'success': return 'fa-circle-check';
            case 'error': return 'fa-circle-exclamation';
            case 'warning': return 'fa-triangle-exclamation';
            default: return 'fa-circle-info';
        }
    }
};

/* ============================
   INI File Editor Module
============================ */

/**
 * Module to manage the INI File Editor.
 */
const iniEditor = {
    currentFile: '',

    /**
     * Initialize the INI editor by setting up event listeners and default values.
     */
    init: function() {
        console.log('Initializing INI file editor...');
        this.setupEventListeners();

        // Set the initial file selector based on the active configuration value.
        const activeConfig = document.getElementById('activeConfig');
        if (activeConfig && activeConfig.textContent) {
            const iniSelector = document.getElementById('iniFileSelector');
            if (iniSelector) {
                iniSelector.value = activeConfig.textContent.trim();
            }
        }
    },

    /**
     * Setup event listeners for the load and save INI file buttons.
     */
    setupEventListeners: function() {
        const loadBtn = document.getElementById('loadIniBtn');
        const saveBtn = document.getElementById('saveIniBtn');

        if (loadBtn) {
            loadBtn.addEventListener('click', () => this.loadIniFile());
            console.log('Load INI button listener added');
        }

        if (saveBtn) {
            saveBtn.addEventListener('click', () => this.saveIniFile());
            console.log('Save INI button listener added');
        }
    },

    /**
     * Load the selected INI file content from the server.
     */
    loadIniFile: async function() {
        const selector = document.getElementById('iniFileSelector');
        const contentArea = document.getElementById('iniContent');
        const statusMsg = document.getElementById('loadIniStatus');
        const fileDisplay = document.getElementById('currentIniFile');

        if (!selector || !contentArea || !statusMsg) {
            Utils.showNotification('INI editor elements not found', 'error');
            return;
        }

        const fileName = selector.value;
        if (!fileName) {
            statusMsg.textContent = 'Please select a file';
            statusMsg.className = 'status-message error';
            return;
        }

        UI.showLoading();
        try {
            const response = await fetch(`/get_ini_content?file=${fileName}`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            if (data.error) {
                throw new Error(data.error);
            }
            contentArea.value = data.content;
            this.currentFile = fileName;
            statusMsg.textContent = `File loaded successfully`;
            statusMsg.className = 'status-message success';

            if (fileDisplay) {
                fileDisplay.textContent = fileName;
            }
            Utils.showNotification(`Loaded ${fileName} successfully`, 'success');
        } catch (error) {
            console.error('Error loading INI file:', error);
            statusMsg.textContent = `Error: ${error.message}`;
            statusMsg.className = 'status-message error';
            Utils.showNotification(error.message, 'error');
        } finally {
            UI.hideLoading();
        }
    },

    /**
     * Save the edited INI file content to the server.
     */
    saveIniFile: async function() {
        const contentArea = document.getElementById('iniContent');
        const statusMsg = document.getElementById('saveIniStatus');

        if (!contentArea || !statusMsg) {
            Utils.showNotification('INI editor elements not found', 'error');
            return;
        }

        if (!this.currentFile) {
            statusMsg.textContent = 'No file loaded';
            statusMsg.className = 'status-message error';
            Utils.showNotification('Please load a file first', 'warning');
            return;
        }

        const content = contentArea.value;
        if (!content.trim()) {
            statusMsg.textContent = 'Content cannot be empty';
            statusMsg.className = 'status-message error';
            Utils.showNotification('INI file content cannot be empty', 'warning');
            return;
        }

        UI.showLoading();
        try {
            const response = await fetch('/save_ini_content', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    file: this.currentFile,
                    content: content
                })
            });
            const result = await response.json();
            if (!response.ok) {
                throw new Error(result.error || 'Failed to save file');
            }
            
            statusMsg.textContent = result.message || 'File saved successfully';
            statusMsg.className = 'status-message success';
            Utils.showNotification(result.message || `Saved ${this.currentFile} successfully`, 'success');

            // If the server indicates configuration was reloaded, update the UI
            if (result.reload_triggered) {
                await this.updateUIAfterReload();
            }
        } catch (error) {
            console.error('Error saving INI file:', error);
            statusMsg.textContent = `Error: ${error.message}`;
            statusMsg.className = 'status-message error';
            Utils.showNotification(error.message, 'error');
        } finally {
            UI.hideLoading();
        }
    },

    /**
     * Updates UI components after an INI file has been saved and configuration reloaded
     * Fetches fresh data from the server
     */
    updateUIAfterReload: async function() {
        try {
            // Fetch updated schedule and announcement data
            const response = await fetch('/get_current_schedule');
            if (!response.ok) {
                throw new Error('Failed to fetch updated schedule');
            }
            
            const data = await response.json();
            if (data.status !== 'success') {
                throw new Error(data.error || 'Unknown error refreshing data');
            }
            
            // Update the times in the schedule editor
            if (scheduleEditor && typeof scheduleEditor.times !== 'undefined') {
                scheduleEditor.times.clear();
                Object.entries(data.times).forEach(([time, type]) => {
                    scheduleEditor.times.set(time, type);
                });
                scheduleEditor.updateScheduleList();
            }
            
            // Update custom types
            if (customTypes && typeof customTypes.types !== 'undefined') {
                customTypes.types.clear();
                Object.entries(data.custom_types).forEach(([name, template]) => {
                    customTypes.types.set(name, template);
                });
                customTypes.updateTypesList();
                customTypes.updateTypeDropdown();
            }
            
            // Update the announcement templates in the form
            const templates = {
                'hour_template': data.announcements.hour,
                'fiftyfive_template': data.announcements.fiftyfive,
                'rules_template': data.announcements.rules,
                'ad_template': data.announcements.ad
            };
            
            Object.entries(templates).forEach(([id, value]) => {
                const element = document.getElementById(id);
                if (element) {
                    element.value = value;
                }
            });
            
            // Update upcoming announcements
            updateUpcomingAnnouncements();
            
            Utils.showNotification('Configuration reloaded and UI updated successfully', 'success');
            
        } catch (error) {
            console.error('Error updating UI after reload:', error);
            Utils.showNotification(`UI update error: ${error.message}`, 'error');
        }
    }
};

/**
 * Global initialization function for the INI editor.
 * This function is attached to the window object so that it is available globally.
 */
function initializeINIEditor() {
    if (typeof iniEditor !== 'undefined') {
        iniEditor.init();
        console.log('INI editor initialized');
    }
    fixSwitchConfigButton();
}
window.initializeINIEditor = initializeINIEditor; // Make the function globally available

/* ============================
   UI Components and Utilities
============================ */

/**
 * UI object handles the initialization and behavior of various UI components.
 */
const UI = {
    /**
     * Initialize UI components.
     */
    init: function() {
        console.log('Initializing UI components...');
        this.setupSidebar();
        this.setupTabs();
        this.setupAlerts();
        this.setupPasswordToggles();
        this.updateClock();
        setInterval(() => this.updateClock(), 1000);
    },

    /**
     * Setup the sidebar toggle for mobile devices.
     */
    setupSidebar: function() {
        const sidebarToggle = document.getElementById('sidebarToggle');
        const sidebar = document.querySelector('.sidebar');
        
        if (sidebarToggle && sidebar) {
            sidebarToggle.addEventListener('click', () => {
                sidebar.classList.toggle('active');
            });
            
            // Close sidebar when clicking a link on mobile.
            document.querySelectorAll('.nav-link').forEach(link => {
                link.addEventListener('click', () => {
                    if (window.innerWidth <= 576) {
                        sidebar.classList.remove('active');
                    }
                });
            });
            window.addEventListener('scroll', () => {
                this.updateActiveNavItem();
            });
        }
    },

    /**
     * Update active navigation item based on scroll position.
     */
    updateActiveNavItem: function() {
        const sections = document.querySelectorAll('.content-section');
        const navLinks = document.querySelectorAll('.nav-link');
        let currentSection = '';
        sections.forEach(section => {
            const sectionTop = section.offsetTop - 100;
            const sectionHeight = section.offsetHeight;
            const sectionId = section.getAttribute('id');
            if (window.scrollY >= sectionTop && window.scrollY < sectionTop + sectionHeight) {
                currentSection = sectionId;
            }
        });
        navLinks.forEach(link => {
            link.classList.remove('active');
            if (link.getAttribute('href') === `#${currentSection}`) {
                link.classList.add('active');
            }
        });
    },

    /**
     * Setup tabbed content.
     */
    setupTabs: function() {
        const tabButtons = document.querySelectorAll('.tab-btn');
        if (tabButtons.length > 0) {
            tabButtons.forEach(button => {
                button.addEventListener('click', () => {
                    const targetTab = button.dataset.tab;
                    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
                    document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));
                    button.classList.add('active');
                    document.getElementById(`${targetTab}-tab`).classList.add('active');
                });
            });
        }
    },

    /**
     * Setup alert dismissal functionality.
     */
    setupAlerts: function() {
        document.querySelectorAll('.alert-close').forEach(button => {
            button.addEventListener('click', function() {
                this.closest('.alert').remove();
            });
        });
        setTimeout(() => {
            document.querySelectorAll('.alert').forEach(alert => {
                alert.style.opacity = '0';
                setTimeout(() => {
                    alert.remove();
                }, 300);
            });
        }, 5000);
    },

    /**
     * Setup password visibility toggles.
     */
    setupPasswordToggles: function() {
        document.querySelectorAll('.password-toggle').forEach(toggle => {
            toggle.addEventListener('click', function() {
                const passwordInput = this.previousElementSibling;
                const icon = this.querySelector('i');
                if (passwordInput.type === 'password') {
                    passwordInput.type = 'text';
                    icon.classList.remove('fa-eye');
                    icon.classList.add('fa-eye-slash');
                } else {
                    passwordInput.type = 'password';
                    icon.classList.remove('fa-eye-slash');
                    icon.classList.add('fa-eye');
                }
            });
        });
    },

    /**
     * Update the clock display.
     */
    updateClock: function() {
        const clockElement = document.getElementById('clock');
        if (!clockElement) return;
        const now = new Date();
        let hours = now.getHours();
        const minutes = now.getMinutes().toString().padStart(2, '0');
        const seconds = now.getSeconds().toString().padStart(2, '0');
        const ampm = hours >= 12 ? 'PM' : 'AM';
        hours = hours % 12 || 12;
        clockElement.textContent = `${hours}:${minutes}:${seconds} ${ampm}`;
    },

    /**
     * Show the loading overlay.
     */
    showLoading: function() {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            overlay.classList.add('active');
        }
    },

    /**
     * Hide the loading overlay.
     */
    hideLoading: function() {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            overlay.classList.remove('active');
        }
    }
};

/**
 * Fix the Switch Config button by ensuring its event listener is correctly set.
 */
function fixSwitchConfigButton() {
    const switchConfigBtn = document.getElementById('switchConfigBtn');
    if (switchConfigBtn) {
        const newBtn = switchConfigBtn.cloneNode(true);
        switchConfigBtn.parentNode.replaceChild(newBtn, switchConfigBtn);
        newBtn.addEventListener('click', async function() {
            const configSelector = document.getElementById('configSelector');
            if (!configSelector) {
                Utils.showNotification('Config selector not found', 'error');
                return;
            }
            const selectedConfig = configSelector.value;
            if (!selectedConfig) {
                Utils.showNotification('Please select a configuration file', 'warning');
                return;
            }
            UI.showLoading();
            try {
                const response = await fetch('/switch_config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ config_file: selectedConfig })
                });
                const result = await response.json();
                if (!response.ok) {
                    throw new Error(result.error || 'Failed to switch configuration');
                }
                Utils.showNotification(`Successfully switched to ${selectedConfig}`, 'success');
                setTimeout(() => window.location.reload(), 1000);
            } catch (error) {
                console.error('Error switching configuration:', error);
                Utils.showNotification(error.message, 'error');
                UI.hideLoading();
            }
        });
        console.log('Switch config button fixed and new listener added');
    }
}

/* ============================
   Schedule Editor Module
============================ */

/**
 * Module for managing the announcement schedule.
 */
const scheduleEditor = {
    times: new Map(),

    /**
     * Initialize the schedule editor.
     */
    init: function() {
        console.log('Initializing schedule editor...');
        this.setupEventListeners();
        this.updateScheduleList();
    },

    /**
     * Setup event listeners for schedule editor actions.
     */
    setupEventListeners: function() {
        const addTimeBtn = document.getElementById('addTimeBtn');
        if (addTimeBtn) {
            addTimeBtn.addEventListener('click', () => this.addTime());
        }
    },

    /**
     * Add a new scheduled announcement time.
     */
    addTime: async function() {
        const timeInput = document.getElementById('newTime');
        const typeSelect = document.getElementById('newType');
        if (!timeInput || !typeSelect) {
            Utils.showNotification('Time input or type select not found', 'error');
            return;
        }
        const time = timeInput.value;
        const type = typeSelect.value;
        if (!time || !type) {
            Utils.showNotification('Please select both time and announcement type', 'warning');
            return;
        }
        UI.showLoading();
        try {
            const response = await fetch('/add_time', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ time, type })
            });
            const result = await response.json();
            if (!response.ok) {
                throw new Error(result.error || 'Failed to add time');
            }
            Utils.showNotification('Time added successfully', 'success');
            await refreshState();
        } catch (error) {
            console.error('Error adding time:', error);
            Utils.showNotification(error.message, 'error');
        } finally {
            UI.hideLoading();
        }
    },

    /**
     * Delete a scheduled announcement time.
     * @param {string} time - The time of the announcement to delete.
     */
    deleteTime: async function(time) {
        if (!confirm(`Are you sure you want to delete the ${time} announcement?`)) {
            return;
        }
        UI.showLoading();
        try {
            const response = await fetch('/delete_time', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ time })
            });
            const result = await response.json();
            if (!response.ok) {
                throw new Error(result.error || 'Failed to delete time');
            }
            Utils.showNotification('Time deleted successfully', 'success');
            await refreshState();
        } catch (error) {
            console.error('Error deleting time:', error);
            Utils.showNotification(error.message, 'error');
        } finally {
            UI.hideLoading();
        }
    },

    /**
     * Update the schedule list in the UI.
     */
    updateScheduleList: function() {
        const scheduleList = document.getElementById('scheduleList');
        const timesTextarea = document.getElementById('times');
        if (!scheduleList || !timesTextarea) {
            console.error('Schedule list or times textarea not found');
            return;
        }
        const timeEntries = [...this.times.entries()].sort();
        let html = '';
        if (timeEntries.length === 0) {
            html = '<div class="schedule-item"><span class="type">No announcements scheduled</span></div>';
        } else {
            timeEntries.forEach(([time, type]) => {
                const typeLabel = type.startsWith('custom:')
                    ? `Custom: ${type.replace('custom:', '')}`
                    : { ':55': 'Color Warning', 'hour': 'Hour Change', 'rules': 'Rules', 'ad': 'Advertisement' }[type] || type;
                html += `
                    <div class="schedule-item" data-type="${type}">
                        <span class="time">${Utils.formatTime(time)}</span>
                        <span class="type">${typeLabel}</span>
                        <div class="actions">
                            <button type="button" class="btn-delete" onclick="scheduleEditor.deleteTime('${time}')">
                                <i class="fa-solid fa-trash-alt"></i>
                            </button>
                        </div>
                    </div>
                `;
            });
        }
        scheduleList.innerHTML = html;
        timesTextarea.value = timeEntries.map(([time, type]) => `${time} = ${type}`).join('\n');
    },

    /**
     * Refresh the schedule from the server.
     * This ensures that UI data is synchronized with server data.
     */
    refreshSchedule: async function() {
        UI.showLoading();
        try {
            const response = await fetch('/update_schedule', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh: true })
            });
            
            const result = await response.json();
            if (!response.ok) {
                throw new Error(result.error || 'Failed to refresh schedule');
            }
            
            // Update the schedule with the latest data
            this.times.clear();
            Object.entries(result.times).forEach(([time, type]) => {
                this.times.set(time, type);
            });
            this.updateScheduleList();
            
            // Update custom types if they're available
            if (result.custom_types && customTypes) {
                customTypes.types.clear();
                Object.entries(result.custom_types).forEach(([name, template]) => {
                    customTypes.types.set(name, template);
                });
                customTypes.updateTypesList();
                customTypes.updateTypeDropdown();
            }
            
            // Update upcoming announcements
            updateUpcomingAnnouncements();
            
            Utils.showNotification('Schedule refreshed successfully', 'success');
        } catch (error) {
            console.error('Error refreshing schedule:', error);
            Utils.showNotification(error.message, 'error');
        } finally {
            UI.hideLoading();
        }
    }
};

/* ============================
   Custom Announcement Types Module
============================ */

/**
 * Module for managing custom announcement types.
 */
const customTypes = {
    types: new Map(),

    /**
     * Initialize custom announcement types.
     */
    init: function() {
        console.log('Initializing custom types...');
        this.setupEventListeners();
        this.updateTypesList();
        this.updateTypeDropdown();
    },

    /**
     * Setup event listeners for adding custom types.
     */
    setupEventListeners: function() {
        const addTypeBtn = document.getElementById('addTypeBtn');
        if (addTypeBtn) {
            addTypeBtn.addEventListener('click', () => this.addType());
        }
    },

    /**
     * Add a new custom announcement type.
     */
    addType: async function() {
        const nameInput = document.getElementById('newTypeName');
        const templateInput = document.getElementById('newTypeTemplate');
        if (!nameInput || !templateInput) {
            Utils.showNotification('Name input or template input not found', 'error');
            return;
        }
        const name = nameInput.value.trim();
        const template = templateInput.value.trim();
        if (!name || !template) {
            Utils.showNotification('Please enter both name and template', 'warning');
            return;
        }
        UI.showLoading();
        try {
            const response = await fetch('/add_custom_type', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, template })
            });
            const result = await response.json();
            if (!response.ok) {
                throw new Error(result.error || 'Failed to add custom type');
            }
            nameInput.value = '';
            templateInput.value = '';
            Utils.showNotification('Custom type added successfully', 'success');
            await refreshState();
        } catch (error) {
            console.error('Error adding custom type:', error);
            Utils.showNotification(error.message, 'error');
        } finally {
            UI.hideLoading();
        }
    },

    /**
     * Update the custom types list in the UI.
     */
    updateTypesList: function() {
        const typesList = document.getElementById('customTypesList');
        const typesTextarea = document.getElementById('customTypes');
        if (!typesList || !typesTextarea) {
            console.error('Types list or types textarea not found');
            return;
        }
        let html = '';
        if (this.types.size === 0) {
            html = '<div class="custom-type-item"><span class="type">No custom types defined</span></div>';
        } else {
            this.types.forEach((template, name) => {
                html += `
                    <div class="custom-type-item">
                        <span class="name">${name}</span>
                        <span class="template">${template}</span>
                    </div>
                `;
            });
        }
        typesList.innerHTML = html;
        typesTextarea.value = [...this.types.entries()].map(([name, template]) => `${name} = ${template}`).join('\n');
    },

    /**
     * Update the dropdown for custom types.
     */
    updateTypeDropdown: function() {
        const typeSelect = document.getElementById('newType');
        if (!typeSelect) {
            console.error('Type select not found');
            return;
        }
        const builtInOptions = Array.from(typeSelect.options).filter(option => !option.value.startsWith('custom:'));
        typeSelect.innerHTML = '';
        builtInOptions.forEach(option => typeSelect.add(option));
        this.types.forEach((_, name) => {
            const option = new Option(`Custom: ${name}`, `custom:${name}`);
            typeSelect.add(option);
        });
    }
};

/* ============================
   Day Configuration Manager Module
============================ */

/**
 * Module to manage day configuration settings.
 */
const dayConfigManager = {
    /**
     * Initialize the day configuration manager.
     */
    init: function() {
        console.log('Initializing day configuration manager...');
        this.setupEventListeners();
        this.updateDayConfigInfo();
    },

    /**
     * Setup event listeners for switching and copying configuration files.
     */
    setupEventListeners: function() {
        const switchConfigBtn = document.getElementById('switchConfigBtn');
        const copyConfigBtn = document.getElementById('copyConfigBtn');
        if (switchConfigBtn) {
            switchConfigBtn.addEventListener('click', () => this.switchConfig());
        }
        if (copyConfigBtn) {
            copyConfigBtn.addEventListener('click', () => this.copyConfig());
        }
    },

    /**
     * Update day configuration info from the server.
     */
    updateDayConfigInfo: async function() {
        const currentDayElement = document.getElementById('currentDay');
        const activeConfigElement = document.getElementById('activeConfig');
        const configStatusElement = document.getElementById('configStatus');
        if (!currentDayElement || !activeConfigElement || !configStatusElement) {
            console.error('Day config info elements not found');
            return;
        }
        try {
            const response = await fetch('/get_day_configs');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            if (data.current_day) {
                const dayInfo = data.current_day;
                currentDayElement.textContent = dayInfo.day_name;
                activeConfigElement.textContent = dayInfo.config_file;
                if (dayInfo.is_operating_day) {
                    configStatusElement.textContent = 'Operating Day';
                    configStatusElement.className = 'status-active';
                } else {
                    configStatusElement.textContent = 'Non-Operating Day';
                    configStatusElement.className = 'status-inactive';
                }
                const configSelector = document.getElementById('configSelector');
                if (configSelector) {
                    configSelector.value = dayInfo.config_file;
                }
            }
            this.updateConfigFileStatus(data.configs);
        } catch (error) {
            console.error('Error loading day configuration info:', error);
            currentDayElement.textContent = 'Error loading';
            activeConfigElement.textContent = 'Error loading';
            configStatusElement.textContent = 'Error';
            configStatusElement.className = 'status-error';
        }
    },

    /**
     * Update the status of configuration files in the UI.
     * @param {Object} configs - An object containing configuration file statuses.
     */
    updateConfigFileStatus: function(configs) {
        if (!configs) return;
        const copyFromSelector = document.getElementById('copyFromSelector');
        if (copyFromSelector) {
            Array.from(copyFromSelector.options).forEach(option => {
                const config = configs[option.value];
                option.disabled = !(config && config.exists);
                if (!option.textContent.includes('✓') && !option.textContent.includes('✗')) {
                    option.textContent = `${option.value.replace('.ini', '')} ${config && config.exists ? '✓' : '✗'}`;
                }
            });
        }
    },

   /**
     * Switch to a different configuration file.
     */
   switchConfig: async function() {
    const configSelector = document.getElementById('configSelector');
    if (!configSelector) {
        Utils.showNotification('Config selector not found', 'error');
        return;
    }
    const selectedConfig = configSelector.value;
    if (!selectedConfig) {
        Utils.showNotification('Please select a configuration file', 'warning');
        return;
    }
    UI.showLoading();
    try {
        const response = await fetch('/switch_config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ config_file: selectedConfig })
        });
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.error || 'Failed to switch configuration');
        }
        Utils.showNotification(`Successfully switched to ${selectedConfig}`, 'success');
        setTimeout(() => window.location.reload(), 1000);
    } catch (error) {
        console.error('Error switching configuration:', error);
        Utils.showNotification(error.message, 'error');
        UI.hideLoading();
    }
},

/**
 * Copy configuration from one file to another.
 */
copyConfig: async function() {
    const copyFromSelector = document.getElementById('copyFromSelector');
    const copyToSelector = document.getElementById('copyToSelector');
    const copyStatus = document.getElementById('copyStatus');
    if (!copyFromSelector || !copyToSelector) {
        Utils.showNotification('Copy selectors not found', 'error');
        return;
    }
    const source = copyFromSelector.value;
    const target = copyToSelector.value;
    if (source === target) {
        if (copyStatus) {
            copyStatus.textContent = 'Source and target cannot be the same';
            copyStatus.className = 'status-message error';
        }
        Utils.showNotification('Source and target cannot be the same', 'warning');
        return;
    }
    if (!confirm(`Are you sure you want to copy ${source} to ${target}? This will overwrite the target configuration.`)) {
        return;
    }
    UI.showLoading();
    try {
        const response = await fetch('/copy_day_config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source, target })
        });
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.error || 'Failed to copy configuration');
        }
        if (copyStatus) {
            copyStatus.textContent = `Successfully copied ${source} to ${target}`;
            copyStatus.className = 'status-message success';
        }
        Utils.showNotification(`Successfully copied ${source} to ${target}`, 'success');
        await this.updateDayConfigInfo();
    } catch (error) {
        console.error('Error copying configuration:', error);
        if (copyStatus) {
            copyStatus.textContent = `Error: ${error.message}`;
            copyStatus.className = 'status-message error';
        }
        Utils.showNotification(error.message, 'error');
    } finally {
        UI.hideLoading();
    }
}
};

/**
* Refresh the state of the configuration interface.
* Called after updates to ensure the UI is synchronized with the server.
*/
async function refreshState() {
try {
    await dayConfigManager.updateDayConfigInfo();
    
    // Additionally fetch the current schedule
    const response = await fetch('/get_current_schedule');
    if (response.ok) {
        const data = await response.json();
        if (data.status === 'success') {
            // Update schedule data
            if (scheduleEditor && typeof scheduleEditor.times !== 'undefined') {
                scheduleEditor.times.clear();
                Object.entries(data.times).forEach(([time, type]) => {
                    scheduleEditor.times.set(time, type);
                });
                scheduleEditor.updateScheduleList();
            }
            
            // Update custom types
            if (customTypes && typeof customTypes.types !== 'undefined') {
                customTypes.types.clear();
                Object.entries(data.custom_types).forEach(([name, template]) => {
                    customTypes.types.set(name, template);
                });
                customTypes.updateTypesList();
                customTypes.updateTypeDropdown();
            }
            
            // Update upcoming announcements
            updateUpcomingAnnouncements();
        }
    }
    
    console.log('State refreshed');
} catch (error) {
    console.error('Error refreshing state:', error);
}
}

/* ============================
Instant Announcement Setup
============================ */

/**
* Setup instant announcement functionality.
*/
function setupInstantAnnouncement() {
console.log('Setting up instant announcement...');
const instantText = document.getElementById('instantText');
const playInstantBtn = document.getElementById('playInstantBtn');
const instantStatus = document.getElementById('instantStatus');
if (!instantText || !playInstantBtn || !instantStatus) {
    console.error('Missing instant announcement elements');
    return;
}
playInstantBtn.addEventListener('click', async () => {
    const text = instantText.value.trim();
    if (!text) {
        instantStatus.textContent = 'Please enter announcement text';
        instantStatus.className = 'status-message error';
        Utils.showNotification('Please enter announcement text', 'warning');
        return;
    }
    try {
        playInstantBtn.disabled = true;
        instantStatus.textContent = 'Playing announcement...';
        instantStatus.className = 'status-message';
        UI.showLoading();
        const response = await fetch('/play_instant', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        });
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const result = await response.json();
        instantStatus.textContent = 'Announcement played successfully';
        instantStatus.className = 'status-message success';
    } catch (error) {
        console.error('Error playing instant announcement:', error);
        instantStatus.textContent = `Error: ${error.message}`;
        instantStatus.className = 'status-message error';
        Utils.showNotification(error.message, 'error');
    } finally {
        playInstantBtn.disabled = false;
        UI.hideLoading();
    }
});
}

/* ============================
Upcoming Announcements Update
============================ */

/**
* Update the upcoming announcements display.
* @param {Object} [colorData=null] - Optional color data for announcements.
*/
function updateUpcomingAnnouncements(colorData = null) {
console.log('Updating upcoming announcements...');
const container = document.getElementById('upcomingList');
if (!container) {
    console.error('Upcoming list container not found');
    return;
}
const timesTextarea = document.getElementById('times');
if (!timesTextarea) {
    console.error('Times textarea not found');
    return;
}
const now = new Date();
const lines = timesTextarea.value.trim().split('\n');
container.innerHTML = '';
const typeLabels = { ':55': 'Color Warning', 'hour': 'Hour Change', 'rules': 'Rules', 'ad': 'Advertisement' };
const upcoming = lines
    .filter(line => line.trim())
    .map(line => {
        const [timeStr, type] = line.split('=').map(part => part.trim());
        const [hours, minutes] = timeStr.split(':').map(Number);
        const scheduleTime = new Date(now);
        scheduleTime.setHours(hours, minutes, 0, 0);
        if (scheduleTime < now) {
            scheduleTime.setDate(scheduleTime.getDate() + 1);
        }
        const minutesUntil = Math.round((scheduleTime - now) / 1000 / 60);
        if (minutesUntil <= 60) {
            return { time: timeStr, type, minutesUntil, scheduleTime };
        }
        return null;
    })
    .filter(item => item !== null)
    .sort((a, b) => a.scheduleTime - b.scheduleTime);
if (upcoming.length === 0) {
    container.innerHTML = '<div class="upcoming-item empty"><span class="type">No announcements scheduled for the next hour</span></div>';
    return;
}
upcoming.forEach(({ time, type, minutesUntil }) => {
    const typeLabel = type.startsWith('custom:')
        ? `Custom: ${type.replace('custom:', '')}`
        : typeLabels[type] || type;
    let colorInfo = '';
    if (colorData && (type === ':55' || type === 'hour')) {
        const colorKey = type === ':55' ? 'color3' : 'color4';
        if (colorData[colorKey] && colorData[colorKey].color) {
            colorInfo = ` (${colorData[colorKey].color})`;
        }
    }
    const itemHtml = `
        <div class="upcoming-item" data-type="${type}">
            <span class="time">${Utils.formatTime(time)}</span>
            <span class="type">${typeLabel}${colorInfo}</span>
            <span class="countdown">in ${Utils.formatMinutes(minutesUntil)}</span>
        </div>
    `;
    container.insertAdjacentHTML('beforeend', itemHtml);
});
}

/* ============================
Document Ready Initialization
============================ */
document.addEventListener('DOMContentLoaded', () => {
UI.init();
initializeINIEditor();
scheduleEditor.init();
customTypes.init();
dayConfigManager.init();
setupInstantAnnouncement();
updateUpcomingAnnouncements();

// Add a manual refresh button for the schedule (optional enhancement)
const configForm = document.getElementById('configForm');
if (configForm) {
    const refreshBtn = document.createElement('button');
    refreshBtn.type = 'button';
    refreshBtn.className = 'btn btn-outline';
    refreshBtn.innerHTML = '<i class="fa-solid fa-sync"></i> Refresh Schedule';
    refreshBtn.style.marginLeft = '10px';
    refreshBtn.addEventListener('click', async () => {
        if (scheduleEditor && typeof scheduleEditor.refreshSchedule === 'function') {
            await scheduleEditor.refreshSchedule();
        } else {
            await refreshState();
        }
    });
    
    const saveConfigBtn = document.getElementById('saveConfigBtn');
    if (saveConfigBtn && saveConfigBtn.parentNode) {
        saveConfigBtn.parentNode.appendChild(refreshBtn);
    }
}
});
