CODEACT_SWE_TESTGEN_PROMPT = """Your goal is to generate a high-quality test suite for the code file: {code_file}. Output the test suite at {test_file}

Your terminal session has started and you're in the repository's root directory. You can use any bash commands or the special interface to help you. Edit all the files you need to and run any checks or tests that you want.
Remember, YOU CAN ONLY ENTER ONE COMMAND AT A TIME. You should always wait for feedback after every command.
When you're satisfied with all of the changes you've made, you can run the following command: <execute_bash> exit </execute_bash>.
Note however that you cannot use any interactive session commands (e.g. vim) in this environment, but you can write scripts and run them. E.g. you can write a python script and then run it with `python <script_name>.py`.

NOTE ABOUT THE EDIT COMMAND: Indentation really matters! When editing a file, make sure to insert appropriate indentation before each line!

IMPORTANT TIPS:
1. First look at other tests to get an idea of how tests are formatted.

2. Next start by trying to generate a high quality test suite at {test_file} that tests {code_file}.
    When you think you've successfully generated a test suite, run coverage on for the current project using {coverage_command}
    Try to maximize coverage of your generated test suite.

3. If you run a command and it doesn't work, try running a different command. A command that did not work once will not work the second time unless you modify it!

4. If you open a file and need to get to an area around a specific line that is not in the first 100 lines, say line 583, don't just use the scroll_down command multiple times. Instead, use the goto 583 command. It's much quicker.

5. DO NOT change the code file {code_file}. ONLY output your test suite to {test_file}.

6. Always make sure to look at the currently open file and the current working directory (which appears right after the currently open file). The currently open file might be in a different directory than the working directory! Note that some commands, such as 'create', open files, so they might change the current  open file.

7. When editing files, it is easy to accidentally specify a wrong line number or to write code with incorrect indentation. Always check the code after you issue an edit to make sure that it reflects what you wanted to accomplish. If it didn't, issue another command to fix it.

[Current directory: /workspace/{workspace_dir_name}]

When you think you have a fully adequate test suite, please run the following command: <execute_bash> exit </execute_bash>.
"""

CODEACT_TESTGEN_PROMPT = """Your goal is to generate a high-quality test suite for the code file: {code_file}. Output the test suite at {test_file}\n'

IMPORTANT: You should ONLY interact with the environment provided to you AND NEVER ASK FOR HUMAN HELP

First look at other tests to get an idea of how tests are formatted.

You should NOT modify any existing test case files. You SHOULD add new test in a NEW file to reproduce the issue.

You should verify that the issue is resolved and any new tests you create pass successfully.

You should NEVER use web browsing or any other web-based tools.

Check your solutions with {coverage_command}.

You should ALWAYS use the default Python interpreter available in the <execute_bash> environment to run code related to the provided issue and/or repository.

When you think you have a fully adequate test suite, please run the following command: <execute_bash> exit </execute_bash>.
"""
