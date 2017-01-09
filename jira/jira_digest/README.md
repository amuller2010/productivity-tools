# JIRA Digest

JIRA Digest sends a summary email with newly created issues and updates on tickets you are watching or that are assigned to you.

## Installation

I recommend using Python 2.7.12, and using a virtualenv to install dependencies.

    git clone git@github.com:amuller2010/productivity-tools.git
    cd productivity-tools/jira/jira_digest
    virtualenv jira-venv
    source jira-venv/bin/activate
    pip install -r requirements.txt

You will need a private key file (`ninabot.pem`) in your jira_digest directory.

## Usage

    (jira-venv)ubuntu@ubuntu14:~/productivity-tools/jira/jira_digest$ python jira_digest.py -h
    Creating Jira Digest email
    usage: jira_digest.py [-h] [--hours HOURS] [--email EMAIL] [--user USER]
    
    Send a JIRA digest email summarizing recent changes.
    
    optional arguments:
      -h, --help     show this help message and exit
      --hours HOURS  summary period in hours preceding now (default: 24)
      --email EMAIL  email address to send summary
      --user USER    jira user to summarize

You may want to edit the default JQL query to suit your needs.
