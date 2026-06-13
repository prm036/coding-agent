#!/usr/bin/env python3

import unittest
import todo

class TestTodoApp(unittest.TestCase):
    def setUp(self):
        # Clear the global list before each test so they don't interfere
        todo.todo_list.clear()
    
    def test_add_task(self):
        todo.add_task('Buy groceries')
        self.assertEqual(todo.todo_list, ['Buy groceries'])

    def test_remove_task(self):
        todo.add_task('Buy groceries')
        todo.remove_task(0)
        self.assertEqual(todo.todo_list, [])

    def test_delete_all_tasks(self):
        todo.add_task('Buy groceries')
        todo.delete_all_tasks()
        self.assertEqual(todo.todo_list, [])

    def test_remind_tasks(self):
        todo.add_task('Buy groceries')
        todo.remind_tasks()
        self.assertEqual(todo.todo_list, ['Buy groceries'])

if __name__ == '__main__':
    unittest.main()