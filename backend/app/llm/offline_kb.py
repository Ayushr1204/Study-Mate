"""Small built-in study knowledge base used ONLY by the offline fallback provider.

It lets the app stay functional (and demonstrable) without a language model.
It is intentionally tiny: six core CS topics.
"""

from __future__ import annotations

from typing import Any

KB: dict[str, dict[str, Any]] = {
    "cpu_scheduling": {
        "title": "CPU Scheduling",
        "keywords": ["cpu scheduling", "process scheduling", "scheduler", "round robin", "fcfs", "sjf", "time quantum"],
        "definition": (
            "CPU scheduling is how an operating system decides which ready process gets the CPU next, "
            "so that the processor stays busy and every process makes fair progress."
        ),
        "analogy": (
            "Think of a single cashier at a busy supermarket. The queue of shoppers is the ready queue. "
            "First-Come-First-Served is the normal queue; Shortest-Job-First is the express lane for people "
            "with a few items; Round Robin is a cashier who serves each customer for at most 30 seconds, then "
            "moves them to the back of the line so nobody waits forever."
        ),
        "steps": [
            "Processes that are ready to run wait in the ready queue.",
            "The scheduler picks one according to its policy (FCFS, SJF, Priority, Round Robin).",
            "The dispatcher performs a context switch and gives that process the CPU.",
            "The process runs until it finishes, blocks on I/O, or its time quantum expires.",
            "The scheduler picks the next process and the cycle repeats.",
        ],
        "key_points": [
            "Goals: high CPU utilisation, high throughput, low waiting and turnaround time, fairness.",
            "Preemptive policies (Round Robin, SRTF) can interrupt a running process; non-preemptive ones cannot.",
            "A very small time quantum causes excessive context-switch overhead; a very large one degrades to FCFS.",
        ],
        "code": {
            "python": (
                "from collections import deque\n\n"
                "def round_robin(burst_times, quantum):\n"
                "    queue = deque(enumerate(burst_times))\n"
                "    clock, finish = 0, {}\n"
                "    while queue:\n"
                "        pid, remaining = queue.popleft()\n"
                "        run = min(quantum, remaining)\n"
                "        clock += run\n"
                "        if remaining - run > 0:\n"
                "            queue.append((pid, remaining - run))\n"
                "        else:\n"
                "            finish[pid] = clock\n"
                "    return finish\n\n"
                "print(round_robin([5, 3, 8], quantum=2))"
            )
        },
        "quiz": [
            {"q": "Which scheduling algorithm gives each process a fixed time slice and then moves it to the back of the queue?",
             "correct": "Round Robin", "wrong": ["First-Come-First-Served", "Shortest Job First", "Priority scheduling"],
             "why": "Round Robin is preemptive and cycles through the ready queue using a time quantum.", "d": "easy"},
            {"q": "What is the main drawback of making the time quantum extremely small in Round Robin?",
             "correct": "Excessive context-switch overhead", "wrong": ["Starvation of short jobs", "Deadlock", "Lower CPU utilisation because processes never run"],
             "why": "Each switch costs time, so a tiny quantum spends most of the CPU on switching rather than useful work.", "d": "medium"},
            {"q": "Which policy gives the minimum average waiting time for a known set of burst times (non-preemptive)?",
             "correct": "Shortest Job First", "wrong": ["First-Come-First-Served", "Round Robin", "Longest Job First"],
             "why": "SJF is provably optimal for average waiting time, but needs burst-time knowledge and can starve long jobs.", "d": "medium"},
            {"q": "A very large time quantum makes Round Robin behave like which algorithm?",
             "correct": "First-Come-First-Served", "wrong": ["Shortest Job First", "Multilevel queue", "Priority scheduling"],
             "why": "If the quantum exceeds every burst time, each process runs to completion in arrival order.", "d": "hard"},
        ],
    },
    "deadlock": {
        "title": "Deadlock",
        "keywords": ["deadlock", "banker's algorithm", "bankers algorithm", "circular wait", "mutual exclusion"],
        "definition": (
            "A deadlock is a state where a set of processes are each waiting for a resource held by another "
            "process in the set, so none of them can ever proceed."
        ),
        "analogy": (
            "Picture four cars arriving at a four-way intersection at the same moment, each blocking the one "
            "to its right. Nobody can move until someone backs up - that is circular wait."
        ),
        "steps": [
            "A process holds one resource and requests another.",
            "The requested resource is held by a second process, which in turn requests the first process's resource.",
            "All four Coffman conditions are now true, so no process can make progress.",
            "The OS must prevent, avoid (Banker's algorithm), detect and recover, or ignore the problem.",
        ],
        "key_points": [
            "Coffman conditions: mutual exclusion, hold and wait, no preemption, circular wait.",
            "Breaking any one condition prevents deadlock.",
            "Banker's algorithm avoids deadlock by only granting requests that leave the system in a safe state.",
        ],
        "code": {
            "python": (
                "import threading\n\n"
                "a, b = threading.Lock(), threading.Lock()\n\n"
                "def worker_1():\n"
                "    with a:\n"
                "        with b:  # takes a then b\n"
                "            pass\n\n"
                "def worker_2():\n"
                "    with a:      # same order as worker_1 -> no circular wait\n"
                "        with b:\n"
                "            pass"
            )
        },
        "quiz": [
            {"q": "Which of these is NOT one of the four necessary conditions for deadlock?",
             "correct": "Preemption", "wrong": ["Mutual exclusion", "Hold and wait", "Circular wait"],
             "why": "The condition is *no* preemption: resources cannot be forcibly taken away.", "d": "easy"},
            {"q": "Banker's algorithm is an example of which deadlock-handling strategy?",
             "correct": "Deadlock avoidance", "wrong": ["Deadlock prevention", "Deadlock detection", "Ignoring deadlock"],
             "why": "It grants a request only if the resulting state is safe.", "d": "medium"},
            {"q": "Forcing every process to request resources in a fixed global order eliminates which condition?",
             "correct": "Circular wait", "wrong": ["Mutual exclusion", "Hold and wait", "No preemption"],
             "why": "A global ordering makes cyclic dependencies impossible.", "d": "medium"},
            {"q": "In a resource-allocation graph with single-instance resources, what indicates a deadlock?",
             "correct": "A cycle in the graph", "wrong": ["A node with no edges", "More processes than resources", "A process with two requests"],
             "why": "With one instance per resource type, a cycle is necessary and sufficient for deadlock.", "d": "hard"},
        ],
    },
    "normalization": {
        "title": "Database Normalization",
        "keywords": ["normalization", "normalisation", "normal form", "1nf", "2nf", "3nf", "bcnf", "functional dependency"],
        "definition": (
            "Normalization is the process of organising relational tables to reduce redundancy and avoid "
            "insert, update and delete anomalies by splitting data according to functional dependencies."
        ),
        "analogy": (
            "Imagine a school keeping one giant register that rewrites each teacher's phone number next to "
            "every student they teach. Normalization is moving the phone number into a single staff directory "
            "and referring to it by teacher ID, so a change is made in exactly one place."
        ),
        "steps": [
            "1NF: every column holds atomic values and rows are uniquely identifiable.",
            "2NF: remove partial dependencies - non-key columns must depend on the whole key.",
            "3NF: remove transitive dependencies - non-key columns must not depend on other non-key columns.",
            "BCNF: every determinant must be a candidate key.",
        ],
        "key_points": [
            "Normalization trades some read performance (more joins) for integrity.",
            "Denormalization is sometimes used deliberately for reporting workloads.",
            "A functional dependency X -> Y means X uniquely determines Y.",
        ],
        "code": {
            "sql": (
                "-- Before: orders(order_id, customer_id, customer_city, item)\n"
                "-- customer_city depends on customer_id (transitive) -> violates 3NF\n"
                "CREATE TABLE customers (customer_id INT PRIMARY KEY, city TEXT);\n"
                "CREATE TABLE orders (order_id INT PRIMARY KEY, customer_id INT REFERENCES customers, item TEXT);"
            )
        },
        "quiz": [
            {"q": "Which normal form removes partial dependencies on a composite primary key?",
             "correct": "Second Normal Form (2NF)", "wrong": ["First Normal Form (1NF)", "Third Normal Form (3NF)", "Boyce-Codd Normal Form"],
             "why": "2NF requires every non-key attribute to depend on the entire key.", "d": "easy"},
            {"q": "A table violates 3NF when it contains...",
             "correct": "A transitive dependency between non-key attributes", "wrong": ["A repeating group in a column", "A composite primary key", "A foreign key"],
             "why": "3NF forbids non-key attributes depending on other non-key attributes.", "d": "medium"},
            {"q": "What is the main purpose of normalization?",
             "correct": "Reduce redundancy and update anomalies", "wrong": ["Speed up every query", "Encrypt sensitive data", "Increase the number of tables"],
             "why": "Storing each fact once avoids inconsistent updates.", "d": "easy"},
            {"q": "BCNF is stricter than 3NF because it requires that...",
             "correct": "Every determinant is a candidate key", "wrong": ["There are no foreign keys", "All attributes are numeric", "Every table has one column"],
             "why": "BCNF closes the 3NF loophole for overlapping candidate keys.", "d": "hard"},
        ],
    },
    "virtual_memory": {
        "title": "Virtual Memory and Paging",
        "keywords": ["virtual memory", "paging", "page table", "page fault", "tlb", "page replacement"],
        "definition": (
            "Virtual memory gives each process its own large, contiguous address space; the OS and hardware map "
            "fixed-size pages of that space onto physical frames, keeping unused pages on disk."
        ),
        "analogy": (
            "A library keeps only the books people are reading on the desk (RAM) and the rest in the basement "
            "stacks (disk). The catalogue (page table) tells you where each book is; a page fault is a trip "
            "down to the basement."
        ),
        "steps": [
            "The CPU issues a virtual address, split into page number and offset.",
            "The MMU looks up the page number in the TLB, then the page table.",
            "If the page is present, the frame number plus offset forms the physical address.",
            "If not, a page fault traps to the OS, which loads the page and may evict another (LRU, FIFO).",
        ],
        "key_points": [
            "The TLB caches recent translations to avoid a page-table walk on every access.",
            "Thrashing occurs when the system spends more time paging than executing.",
            "Belady's anomaly: FIFO can produce more faults with more frames.",
        ],
        "code": {
            "python": (
                "def lru_faults(pages, frames):\n"
                "    memory, faults = [], 0\n"
                "    for p in pages:\n"
                "        if p in memory:\n"
                "            memory.remove(p)\n"
                "        else:\n"
                "            faults += 1\n"
                "            if len(memory) == frames:\n"
                "                memory.pop(0)\n"
                "        memory.append(p)\n"
                "    return faults\n\n"
                "print(lru_faults([1, 2, 3, 1, 4, 2], frames=3))"
            )
        },
        "quiz": [
            {"q": "What does the TLB cache?",
             "correct": "Recent virtual-to-physical page translations", "wrong": ["Recently used disk blocks", "CPU instructions", "Process control blocks"],
             "why": "It avoids a full page-table walk on most memory accesses.", "d": "easy"},
            {"q": "What event occurs when a referenced page is not in physical memory?",
             "correct": "A page fault", "wrong": ["A segmentation fault", "A context switch", "A TLB flush"],
             "why": "The OS handles the fault by loading the page from disk.", "d": "easy"},
            {"q": "Thrashing happens when...",
             "correct": "The system spends more time swapping pages than executing", "wrong": ["The CPU is idle", "The TLB is too large", "Too few processes are running"],
             "why": "The combined working sets exceed physical memory.", "d": "medium"},
            {"q": "Belady's anomaly is associated with which replacement policy?",
             "correct": "FIFO", "wrong": ["LRU", "Optimal", "Second chance with stack property"],
             "why": "FIFO lacks the stack property, so more frames can cause more faults.", "d": "hard"},
        ],
    },
    "recursion": {
        "title": "Recursion",
        "keywords": ["recursion", "recursive", "base case", "call stack"],
        "definition": (
            "Recursion is a technique where a function solves a problem by calling itself on a smaller instance "
            "of the same problem until it reaches a base case that can be answered directly."
        ),
        "analogy": (
            "Russian nesting dolls: to count how many dolls there are, open the outer doll, count 1, then ask "
            "the same question of the doll inside. The smallest solid doll is the base case."
        ),
        "steps": [
            "Define the base case that stops the recursion.",
            "Define the recursive case that reduces the problem towards the base case.",
            "Each call is pushed on the call stack and waits for the inner call to return.",
            "Results propagate back up as the stack unwinds.",
        ],
        "key_points": [
            "Missing or unreachable base cases cause stack overflow.",
            "Overlapping subproblems (e.g. naive Fibonacci) can be fixed with memoization.",
            "Any recursion can be rewritten iteratively with an explicit stack.",
        ],
        "code": {
            "python": (
                "def factorial(n: int) -> int:\n"
                "    if n <= 1:          # base case\n"
                "        return 1\n"
                "    return n * factorial(n - 1)  # recursive case\n\n"
                "print(factorial(5))  # 120"
            )
        },
        "quiz": [
            {"q": "What stops a recursive function from calling itself forever?",
             "correct": "A base case", "wrong": ["A loop counter", "A global variable", "The garbage collector"],
             "why": "The base case returns without another recursive call.", "d": "easy"},
            {"q": "What error typically results from infinite recursion?",
             "correct": "Stack overflow", "wrong": ["Memory leak in the heap only", "Syntax error", "Division by zero"],
             "why": "Each call adds a frame to the finite call stack.", "d": "easy"},
            {"q": "Which technique speeds up recursion with overlapping subproblems?",
             "correct": "Memoization", "wrong": ["Loop unrolling", "Inlining", "Sharding"],
             "why": "Caching results avoids recomputing identical subproblems.", "d": "medium"},
            {"q": "What is the time complexity of naive recursive Fibonacci?",
             "correct": "Exponential, O(2^n)", "wrong": ["Linear, O(n)", "Logarithmic, O(log n)", "Quadratic, O(n^2)"],
             "why": "Each call branches into two overlapping calls.", "d": "hard"},
        ],
    },
    "binary_search": {
        "title": "Binary Search",
        "keywords": ["binary search", "bisect", "sorted array search"],
        "definition": (
            "Binary search finds a target in a sorted array by repeatedly comparing it with the middle element "
            "and discarding the half that cannot contain the target."
        ),
        "analogy": (
            "It is the 'higher or lower' guessing game: pick a number from 1-100 by always guessing the middle. "
            "Each answer removes half of the remaining possibilities."
        ),
        "steps": [
            "Set low and high to the ends of the sorted array.",
            "Compute mid = (low + high) // 2 and compare arr[mid] with the target.",
            "If equal, return mid; if the target is smaller, set high = mid - 1; otherwise low = mid + 1.",
            "Stop when low > high - the target is absent.",
        ],
        "key_points": [
            "Requires sorted input; runs in O(log n) time and O(1) extra space.",
            "Classic bugs: integer overflow of low+high in fixed-width ints, and off-by-one boundaries.",
        ],
        "code": {
            "python": (
                "def binary_search(arr, target):\n"
                "    low, high = 0, len(arr) - 1\n"
                "    while low <= high:\n"
                "        mid = (low + high) // 2\n"
                "        if arr[mid] == target:\n"
                "            return mid\n"
                "        if arr[mid] < target:\n"
                "            low = mid + 1\n"
                "        else:\n"
                "            high = mid - 1\n"
                "    return -1"
            )
        },
        "quiz": [
            {"q": "What is the worst-case time complexity of binary search?",
             "correct": "O(log n)", "wrong": ["O(n)", "O(n log n)", "O(1)"],
             "why": "The search space halves at every step.", "d": "easy"},
            {"q": "What precondition must hold for binary search to work?",
             "correct": "The array is sorted", "wrong": ["The array has unique values", "The array length is a power of two", "The array holds integers"],
             "why": "The discard-half logic relies on ordering.", "d": "easy"},
            {"q": "In a sorted array of 1,000,000 items, roughly how many comparisons does binary search need at most?",
             "correct": "About 20", "wrong": ["About 1,000", "About 500,000", "About 2"],
             "why": "log2(1,000,000) is about 20.", "d": "medium"},
            {"q": "Why is `mid = low + (high - low) // 2` preferred in fixed-width integer languages?",
             "correct": "It avoids overflow of low + high", "wrong": ["It is faster on sorted data", "It handles duplicates", "It avoids recursion"],
             "why": "low + high can exceed the integer range for very large arrays.", "d": "hard"},
        ],
    },
}


def match_topic(text: str) -> str | None:
    """Return the KB key whose keywords best match the text, or None."""
    lowered = text.lower()
    best, best_score = None, 0
    for key, entry in KB.items():
        score = sum(len(k) for k in entry["keywords"] if k in lowered)
        if entry["title"].lower() in lowered:
            score += len(entry["title"])
        if score > best_score:
            best, best_score = key, score
    return best
