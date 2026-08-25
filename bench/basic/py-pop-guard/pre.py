"""Singly linked list."""


class Node:
    def __init__(self, value, nxt=None):
        self.value = value
        self.next = nxt


class LinkedList:
    def __init__(self):
        self.head = None
        self.size = 0

    def push(self, value):
        self.head = Node(value, self.head)
        self.size += 1

    def pop(self):
        if self.head is None:
            raise IndexError("pop from empty list")
        node = self.head
        self.head = node.next
        self.size -= 1
        return node.value

    def __len__(self):
        return self.size


ll = LinkedList()
ll.push(1)
print(ll.pop(), len(ll))
try:
    ll.pop()
except Exception as e:
    print(type(e).__name__, e)
