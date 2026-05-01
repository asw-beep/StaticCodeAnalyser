# Static Code Analyzer (Mini Lint Tool)

## Goal

Build a Python-based static analyzer that parses source code and detects:

- Unused variables
- Dead code
- Basic bug risks like division by zero

## Phase 1: Requirements (2-3 days)

### Functional Requirements

- Accept a Python file (.py)
- Parse it using Python AST (ast module)
- Output warnings like:
  - Unused variable 'x' at line 10
  - Unreachable code detected after return
  - Possible division by zero at line 25

### Non-Functional Requirements

- Fast (analyze small files in <1 sec)
- CLI-based tool initially
- Clean, readable output

### Deliverables

- Requirement document (1-2 pages)
- List of rules to implement

## Phase 2: System Design (2-3 days)

### Architecture Overview

Input Code -> AST Parser -> Rule Engine -> Report Generator -> Output

### Core Modules

1. Parser Module
   - Uses ast.parse()
   - Converts code into AST

2. Analyzer Engine
   - Traverses AST using ast.NodeVisitor
   - Applies rules

3. Rule System
   - Each rule is a separate class:
     - UnusedVariableRule
     - DeadCodeRule
     - DivisionByZeroRule

4. Reporter
   - Formats output
   - Displays line numbers and issues

### Key Design Decision

- Keep rules modular for scalability

## Phase 3: Implementation (7-10 days)

### Milestone 1: AST Understanding (1-2 days)

- Learn ast.parse(), ast.dump()
- Understand node types: Assign, Name, BinOp, Return
- Practice printing AST of sample code

### Milestone 2: AST Traversal (2 days)

- Implement Analyzer class using ast.NodeVisitor
- Track:
  - Variables assigned
  - Variables used

### Milestone 3: Unused Variable Detection (2 days)

- Store assigned variables
- Track used variables
- Compute unused = assigned - used
- Handle edge cases:
  - Function parameters
  - Loop variables

### Milestone 4: Dead Code Detection (2-3 days)

- Detect code after:
  - return
  - break
  - continue

Example:

```python
def f():
    return 5
    print("dead")
```

### Milestone 5: Division By Zero Detection (2-3 days)

- Analyze BinOp nodes
- Identify division operations
- Check right operand:
  - Constant 0 -> definite issue
  - Variable -> possible issue

### Milestone 6: CLI Tool (1 day)

- Use argparse
- Command:

```bash
python analyzer.py test.py
```

Example Output:

```text
[WARNING] Unused variable 'x' at line 4
[ERROR] Division by zero at line 10
```

## Phase 4: Testing (3-4 days)

### Types of Testing

1. Unit Testing
   - Test each rule independently

2. Integration Testing
   - Run tool on sample Python files

3. Edge Case Testing
   - Nested functions
   - Loops
   - Conditional branches

### Deliverables

- Test files with expected outputs

## Phase 5: Deployment (2-3 days)

### Packaging

- Make project installable using pip

Command:

```bash
pip install .
```

### Optional

- Create GitHub repository
- Add README with:
  - Usage
  - Examples
  - Screenshots

## Phase 6: Enhancements (Optional but High Value)

### Advanced Features

- Multi-file analysis
- Detect:
  - Unused imports
  - Shadowed variables
  - Infinite loops
- Add severity levels:
  - INFO
  - WARNING
  - ERROR

### Next-Level Upgrade

- Add support for C/C++ using Clang-based analysis concepts

## Timeline Summary (Waterfall)

- Requirements: 2-3 days
- Design: 2-3 days
- Implementation: 7-10 days
- Testing: 3-4 days
- Deployment: 2-3 days

Total Duration: 16-23 days

## Resume Bullet

Built a modular static code analysis tool using Python AST traversal to detect unused variables, unreachable code, and runtime risks, designing a rule-based engine inspired by compiler analysis techniques.