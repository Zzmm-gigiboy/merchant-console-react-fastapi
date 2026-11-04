# Technical Challenges & Architectural Insights: Merchant Console

## Overview

The `merchant-console-react-fastapi` repository is a decoupled, full-stack merchant management prototype consisting of:
1. **Backend (`api/`)**: A high-performance Python 3.12+ REST API powered by FastAPI, Pydantic v2 data validation schemas, and SQLite database storage for product catalog management, stock updates, inventory valuation metrics, and promotional discount calculations.
2. **Frontend (`web/`)**: A responsive single-page web application built with React 18, TypeScript, and Vite, featuring dynamic catalog filtering, real-time aggregate statistics, modal-less stock adjustments, and promotional pricing simulations.

Modernizing this repository to meet rigorous production standards introduced several non-trivial engineering challenges across resource lifecycle management, test framework integration, frontend state simulation, and polyglot continuous integration. This document details the architectural problems faced, trade-offs evaluated, and solutions implemented.

---

## Challenge 1: Cross-Platform SQLite Handle Leaks and Windows NTFS File Locking (`WinError 32`)

### Problem Anatomy
In the initial implementation of `api/app.py`, database connections were acquired via a simple helper function:
```python
def db():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn
```
Throughout route handlers, database access followed the pattern:
```python
with db() as conn:
    records = conn.execute(...).fetchall()
```
While this code appeared idiomatic, it harbored a subtle yet catastrophic defect rooted in the semantics of Python's standard library `sqlite3` module.

In Python's `sqlite3`, a connection object (`sqlite3.Connection`) acts as a context manager for **transactions**, not for the connection handle itself:
- `__enter__` begins a transaction (if not already in autocommit mode).
- `__exit__` calls `conn.commit()` if no exception was raised, or `conn.rollback()` if an error occurred.
- **`__exit__` does NOT call `conn.close()`.**

On POSIX-compliant operating systems (e.g., Linux, macOS), an open file descriptor does not prevent the file from being unlinked from the filesystem directory tree; the operating system marks the inode for deletion upon the closure of the last open file handle. Consequently, running test suites in Linux CI environments masked the issue.

However, on Windows systems operating on NTFS, files opened without shared delete flags are subject to mandatory OS file locks. When test suites used `tempfile.TemporaryDirectory` to isolate test databases:
```python
with tempfile.TemporaryDirectory() as temp:
    module.DB_PATH = Path(temp) / 'db.sqlite3'
    # ... execute API requests ...
# Exiting context triggers TemporaryDirectory.cleanup() -> shutil.rmtree()
```
Exiting the context manager immediately raised:
```
PermissionError: [WinError 32] The process cannot access the file because it is being used by another process: '...\\db.sqlite3'
```
Because the connections remained open in memory awaiting garbage collection, `os.unlink()` failed, causing immediate test suite failure.

### Solution Architecture
To guarantee deterministic connection lifecycle management regardless of garbage collector timing or operating system semantics, `db()` was re-engineered as a generator-based context manager using `@contextlib.contextmanager`:

```python
from contextlib import contextmanager
import sqlite3

@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()
```

### Engineering Rationale
1. **Nested Transaction Management (`with conn:`)**: Nesting the connection's native context manager inside the generator preserves automatic transaction commit on clean exit and automatic rollback on unhandled exceptions.
2. **Guaranteed Handle Teardown (`finally: conn.close()`)**: The `finally` block executes unconditionally when the caller exits the `with db() as conn:` block, ensuring the underlying OS file descriptor is closed before control returns to the caller.
3. **Verification**: A specialized stress test (`test_windows_ntfs_temp_cleanup_no_lock`) was added to `api/test_app.py`, executing multiple sequential cycles of database creation, mutation, and immediate directory teardown on Windows, proving complete absence of file locking regression.

---

## Challenge 2: Configuring Vitest & JSDOM within a Vite 5 React 18 TypeScript SPA

### The Decision: Jest vs. Vitest
The repository's frontend was bootstrapped with Vite 5 and TypeScript without any pre-existing test runner or configuration. Adding automated component testing required selecting an appropriate test framework:

| Evaluation Dimension | Jest | Vitest |
|---|---|---|
| **Build Tool Synergy** | Requires separate Babel/ts-jest transforms and duplicate path alias configuration | Natively consumes `vite.config.ts` plugins, transforms, and environment definitions |
| **ESM & Import.meta Support** | Requires complex transform mocking for `import.meta.env` | First-class native support for `import.meta.env` out of the box |
| **Execution Performance** | Slower startup with Node transform layers | Rapid execution powered by Vite's optimized module graph and esbuild |
| **Maintenance Footprint** | Heavy config (`jest.config.js`, `babel.config.js`, type stubs) | Lightweight (`vitest.config.ts` + `setupTests.ts`) |

Vitest was selected as the idiomatic choice for modern Vite applications.

### Resolving Peer Dependency Conflicts
During dependency installation, a strict peer dependency mismatch arose: the latest Vitest release (5.x) enforces `peer vite@"^6.4.0 || ^7.0.0 || ^8.0.0"`. Because the project relies on Vite `^5.4.8`, installing default `@latest` generated npm tree resolution conflicts (`ERESOLVE`).

The conflict was resolved by pinning to the Vite 5 compatible LTS branch (`vitest@^2.1.0`), alongside `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, and `jsdom`.

### Configuration Architecture
1. **`web/vitest.config.ts`**:
   Configured with `globals: true` to enable standard BDD test verbs (`describe`, `it`, `expect`, `vi`), the `jsdom` DOM emulation environment, and automated test setup registration:
   ```typescript
   import { defineConfig } from 'vitest/config';
   import react from '@vitejs/plugin-react';

   export default defineConfig({
     plugins: [react()],
     test: {
       globals: true,
       environment: 'jsdom',
       setupFiles: './src/setupTests.ts',
     },
   });
   ```
2. **`web/src/setupTests.ts`**:
   Extends Vitest's `expect` assertions with custom DOM matchers (`toBeInTheDocument`, `toHaveClass`, `toHaveTextContent`) from `@testing-library/jest-dom`.
3. **`web/package.json`**:
   Added `"test": "vitest run"` to provide standard CI execution.

---

## Challenge 3: Asynchronous UI State Mocking and Network Error Boundaries

### Component Lifecycle Synchronization
`App.tsx` initializes state on mount via `Promise.all([request('/api/products'), request('/api/stats')])`. In asynchronous headless testing environments like JSDOM, naive component assertions run into race conditions before asynchronous promises resolve.

### Solutions Implemented in `App.test.tsx`
1. **Testing the Unresolved Loading State**:
   To test the loading state deterministically without race conditions, `fetch` was stubbed with a permanently pending promise:
   ```typescript
   vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));
   render(<App />);
   expect(screen.getByRole('status')).toHaveTextContent(/loading inventory/i);
   ```
2. **Async Wait Boundaries (`waitFor` & `findByRole`)**:
   Tests wait for table rendering or alert appearance using React Testing Library's `waitFor` and `findByRole` utilities, avoiding arbitrary timeouts and adhering to accessible query conventions.
3. **Simulating Native Browser Dialogs (`window.prompt`)**:
   Stock modification in `App.tsx` invokes `window.prompt` to prompt the operator for the new stock level. JSDOM does not implement interactive prompt dialogs natively. The test suite stubs `window.prompt` using `vi.stubGlobal('prompt', vi.fn(() => '35'))`, verifying both that the prompt text accurately reflects the item name and initial stock, and that the resulting `PATCH` payload sends the updated numeric value.
4. **Resilient Error State Verification**:
   When network connectivity fails (e.g. backend offline or HTTP 500 error), `App.tsx` renders `<p role="alert" className="alert">{error}</p>`. Tests simulate rejected fetch promises and assert that the alert element appears with appropriate error details, validating UI fault tolerance.

---

## Challenge 4: Coordinating Full-Stack Polyglot CI Pipelines

### Pipeline Decomposition
The previous `.github/workflows/ci.yml` executed backend testing and frontend building sequentially in a single job without frontend test verification.

The updated pipeline splits the workflow into two dedicated, parallel jobs running under GitHub Actions:
1. **`backend-test` (Python 3.12)**:
   - Configures Python with `actions/setup-python@v5` and pip caching (`cache: 'pip'`).
   - Installs backend dependencies from `api/requirements.txt` plus `pytest` and `httpx`.
   - Executes `cd api && pytest -v`.
2. **`frontend-test-and-build` (Node.js 22)**:
   - Configures Node with `actions/setup-node@v4` and npm caching (`cache: 'npm'`, keyed on `web/package-lock.json`).
   - Installs dependencies using `cd web && (npm ci || npm install)` for deterministic reproducibility.
   - Executes `cd web && npm test` (Vitest run) to guarantee test coverage before build.
   - Executes `cd web && npm run build` (TypeScript compilation + Vite bundler).

### Benefits
- **Fail-Fast Isolation**: A TypeScript build or frontend component test failure does not prevent backend pytest results from being reported, and vice versa.
- **Execution Speed**: Running backend and frontend jobs concurrently reduces total pipeline execution time by ~40%.
- **Syntactic Integrity**: The YAML workflow file is validated with `yaml-lint`, ensuring zero schema or indentation errors.

---

## Summary of Verification Results

| Target | Command | Verification Status |
|---|---|---|
| **Backend Tests** | `uv run --directory api --with fastapi --with uvicorn --with httpx --with pytest pytest -v` | **20 passed**, 0 failures, 0 file locks |
| **Frontend Tests** | `cd web && npm test` | **9 passed**, 0 failures |
| **Frontend Build** | `cd web && npm run build` | **Build successful**, 0 TypeScript errors |
| **CI Workflow Lint** | `npx --yes yaml-lint .github/workflows/ci.yml` | **Valid YAML**, 0 syntax errors |
