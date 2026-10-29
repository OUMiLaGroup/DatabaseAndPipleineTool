# Fall 2026 Label Consistency Unit Tests

This folder contains the same label-consistency unit test implemented in three programming languages:

- Python
- JavaScript
- C#

The purpose of these tests is to demonstrate the same feature using three different unit-testing frameworks.

## What the Tests Check

The tests simulate object detections that could come from a computer-vision model or CVAT annotation workflow.

Each detection has:

- An object type, such as `pedestrian`, `car`, `cyclist`, or `truck`
- Width
- Height
- Length
- Confidence score

The test code checks whether the object's dimensions and confidence are reasonable for the label that was assigned.

For example:

- A normal-sized pedestrian should pass.
- A pedestrian with car-sized dimensions should be flagged.
- A normal-sized car should pass.
- A car with pedestrian-sized dimensions should be flagged.
- A detection with very low confidence should be flagged.
- An unknown object type should be flagged.

These are demonstration validation rules. The size ranges are intentionally simple and are not meant to be exact real-world engineering specifications.

## Test Files

### Python

File:

```text
test_label_consistency.py
```

Framework:

```text
unittest
```

### JavaScript

File:

```text
test_label_consistency.test.js
```

Framework:

```text
node:test
```

Node.js 18 or newer is required.

### C#

Files:

```text
LabelConsistencyTests.cs
LabelConsistencyTests.csproj
```

Framework:

```text
xUnit
```

The C# project targets:

```text
.NET 8.0
```

## Test Cases

Each language version runs the same six logical tests.

### 1. Normal Pedestrian

Creates a pedestrian with reasonable dimensions and a high confidence score.

Expected result:

```text
No issues are found.
```

### 2. Oversized Pedestrian

Creates a detection labeled as a pedestrian, but gives it dimensions closer to a car.

Expected result:

```text
The detection is flagged.
```

### 3. Normal Car

Creates a car with reasonable dimensions and a high confidence score.

Expected result:

```text
No issues are found.
```

### 4. Undersized Car

Creates a detection labeled as a car, but gives it dimensions closer to a pedestrian.

Expected result:

```text
The detection is flagged.
```

### 5. Low Confidence

Creates a cyclist with reasonable dimensions but a confidence score below the minimum threshold.

Expected result:

```text
The detection is flagged for low confidence.
```

### 6. Unknown Object Type

Creates a detection with an object type that does not have any defined size rules.

Expected result:

```text
The detection is flagged as an unknown object type.
```

---

# Running the Tests in GitHub Codespaces

GitHub Codespaces gives you a VS Code development environment directly in your browser.

## 1. Open the Repository

Open the GitHub repository:

```text
DatabaseAndPipelineTool-GroupE-FA26
```

Make sure you are working on the correct branch:

```text
mila/main
```

## 2. Open a Codespace

On GitHub:

1. Click the green **Code** button.
2. Select the **Codespaces** tab.
3. Create or open a Codespace for the repository.

GitHub will open a VS Code environment in your browser.

## 3. Open the Terminal

In Codespaces, open a terminal by using one of these methods:

- Click **Terminal > New Terminal**
- Press `Ctrl + backtick`
- Press `Ctrl + Shift + P`, search for `Terminal: Create New Terminal`, and press Enter

## 4. Update Your Local Codespace

A Codespace can sometimes be behind the latest version of the GitHub repository.

From the repository root, run:

```bash
git pull
```

If you want to verify the current branch:

```bash
git branch --show-current
```

You should see:

```text
mila/main
```

## 5. Move Into the Test Folder

From the repository root:

```bash
cd tests/unit/fall26
```

Verify the files are present:

```bash
ls
```

You should see:

```text
LabelConsistencyTests.cs
LabelConsistencyTests.csproj
test_label_consistency.py
test_label_consistency.test.js
```

---

# Running the Python Tests

From:

```text
tests/unit/fall26
```

run:

```bash
python3 -m unittest -v test_label_consistency.py
```

A successful result should end with something similar to:

```text
Ran 6 tests

OK
```

The current Python test suite contains:

```text
6 tests
6 passed
0 failed
```

---

# Running the JavaScript Tests

First, you can check your Node.js version with:

```bash
node --version
```

Then run:

```bash
node --test test_label_consistency.test.js
```

A successful result should include:

```text
tests 6
pass 6
fail 0
```

The current JavaScript test suite contains:

```text
6 tests
6 passed
0 failed
```

---

# Running the C# Tests

The C# project targets .NET 8.

You can first check which .NET SDK is installed:

```bash
dotnet --version
```

Then try:

```bash
dotnet test LabelConsistencyTests.csproj -v normal
```

## If the Codespace Does Not Have the .NET 8 Runtime

The default GitHub Codespace may have newer .NET versions installed but not the .NET 8 runtime required by this project.

If you see an error similar to:

```text
You must install or update .NET to run this application.

Framework: 'Microsoft.NETCore.App', version '8.0.0'
```

use Docker to run the C# tests with the correct .NET 8 environment.

From the `tests/unit/fall26` folder, run:

```bash
docker run --rm \
  -v "$PWD":/src \
  -w /src \
  mcr.microsoft.com/dotnet/sdk:8.0 \
  dotnet test LabelConsistencyTests.csproj -v normal
```

The first time this command is run, Docker may need to download the .NET 8 image and restore the xUnit packages.

A successful result should include:

```text
Test Run Successful.
Total tests: 6
Passed: 6
```

The current C# test suite contains:

```text
6 tests
6 passed
0 failed
```

---

# Current Test Results

All three implementations have been run successfully.

| Language | Tests | Passed | Failed |
|---|---:|---:|---:|
| Python | 6 | 6 | 0 |
| JavaScript | 6 | 6 | 0 |
| C# | 6 | 6 | 0 |
| **Total** | **18** | **18** | **0** |

---

# Quick Command Reference

From the repository root:

```bash
git pull
cd tests/unit/fall26
```

Run Python:

```bash
python3 -m unittest -v test_label_consistency.py
```

Run JavaScript:

```bash
node --test test_label_consistency.test.js
```

Run C# directly if .NET 8 is available:

```bash
dotnet test LabelConsistencyTests.csproj -v normal
```

Or run C# using Docker:

```bash
docker run --rm \
  -v "$PWD":/src \
  -w /src \
  mcr.microsoft.com/dotnet/sdk:8.0 \
  dotnet test LabelConsistencyTests.csproj -v normal
```

## Summary

These tests verify a simple label-consistency feature across three programming languages.

All three versions perform the same six logical checks, and all three currently pass successfully.
