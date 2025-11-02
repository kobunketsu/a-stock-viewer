import os
import sys
from termcolor import colored
import time
import datetime
from datetime import timedelta

def cmd(idx=1):
    return sys._getframe(idx).f_code.co_name

# def printFunc(s):
    # print('{} {}'.format(s.cmd(2), s))
    
def printSucess(s):
    print(colored(s, 'green'))

def printWarn(s):
    print(colored(s, 'yellow'))

def printError(s):
    print(colored(s, 'red'))    

def printTaskStart():
    str = '{} start'.format(cmd(2))
    print(colored(str, 'yellow'))

def printTaskDone():
    str = '{} done'.format(cmd(2))
    print(colored(str, 'yellow'))

# 装饰器
# 定义在函数前后，嵌入函数

# @start_message
# def my_method():
#     print("Hello from my method!")
def start_message(func):
    def wrapper(*args, **kwargs):
        print(f"Start of method: {func.__name__}")
        result = func(*args, **kwargs)
        return result
    return wrapper    

# @end_message
# def my_method():
#     print("Hello from my method!")    
def end_message(func):
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        print(f"End of method: {func.__name__}")
        return result
    return wrapper

def run_start_end_message():
    def start_end_message(func):
        def wrapper(*args, **kwargs):
            print(colored(f"PID: {os.getpid()} Start of method: {func.__name__} date: {datetime.datetime.now()}", 'green'))
            
            start = time.time()

            result = func(*args, **kwargs)

            end = time.time()                
            runtime = str(timedelta(seconds=end-start))
            print(colored(f"PID: {os.getpid()} End of method: {func.__name__} date: {datetime.datetime.now()} runtime: {runtime} seconds", 'blue'))
            return result
        return wrapper 
    return start_end_message  
