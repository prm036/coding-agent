#!/usr/bin/env python3

todo_list = []

def add_task(task):
    todo_list.append(task)

def remove_task(index):
    if 0 <= index < len(todo_list):
        del todo_list[index]

def delete_all_tasks():
    global todo_list
    todo_list = []

def remind_tasks():
    for task in todo_list:
        print(task)
