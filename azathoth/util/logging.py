import json
import datetime


logLevels = {
    'debug': 0,
    'trace': 1,
    'info': 2,
    'warn': 3,
    'error': 4,
    'fatal': 5
}

currentLogLevel = logLevels['info']

def format_log_message(message, level):
    return f"{datetime.datetime.now().isoformat()} [{level}] {message}"

def log(message, level):
    if currentLogLevel <= logLevels[level]:
        print(format_log_message(message, level))

def trace_log(message):
    if currentLogLevel <= logLevels['trace']:
        print(format_log_message(message, logLevels['trace']))
        
def debug_log(message):
    if currentLogLevel <= logLevels['debug']:
        print(format_log_message(message, logLevels['debug']))
        
def info_log(message):
    if currentLogLevel <= logLevels['info']:
        print(format_log_message(message, logLevels['info']))
        
def warn_log(message):
    if currentLogLevel <= logLevels['warn']:
        print(format_log_message(message, logLevels['warn']))
        
def error_log(message):
    if currentLogLevel <= logLevels['error']:
        print(format_log_message(message, logLevels['error']))
        
def fatal_log(message):
    if currentLogLevel <= logLevels['fatal']:
        print(format_log_message(message, logLevels['fatal']))
        
def set_log_level(level):
    global currentLogLevel
    currentLogLevel = logLevels[level]
    
def get_log_level():
    global currentLogLevel
    return currentLogLevel

def get_log_level_string():
    global currentLogLevel
    for key, value in logLevels.items():
        if value == currentLogLevel:
            return key
    return None

def get_log_levels():
    global logLevels
    return logLevels

