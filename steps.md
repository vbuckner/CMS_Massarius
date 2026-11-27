restrictions
- do not use libraries (python orotherwise) where you dont need them
- my_sql - local server only
- outlook via logged in and python library (we have no choice)
- do not read emails etc to claude cloud, only remain local
- anything llm is installed with qwen - try to use this to analyse the emails
- simple python web page for interaction
- if a step is done, add a tick after the '-'
- update the version number small amounts unless instructed otherwise
- ✓ hold an info md for claude (you) to read and remember
- ✓ hold a change log per version - summary of change(s)

- Info for user
  - cd /d C:\Dev\GIT\CMS_Massarius
    python server.py
  - net start MySQL80

  - To reclassify/tag all emails -- note takes approx 2 hours, may be more (so plug in)
    - python scan.py --retag all --log logs/scan.log

version: v 0.0.4

- ✓ info icon
  - ✓ ccs 
    - ✓ letter i in white text, 
    - ✓ light blue background, 
    - ✓ looks like a circle, 
    - ✓ border of dark gray 1 pixel
    - ✓ on mouse hover
      - ✓ glow the blue (shadow?)
    - ✓ on click toggle
      - ✓ pop up info - see section where required
      
- ✓ prodcue a webpage
  - ✓ title : CMS Massarius
    - ✓ version number in smaller text after
    - ✓ info button
      - CMS Thoughts for Massarius, via email scanner
        possibly a brain type interface
        can run agents
  
  - ✓ tabs
    - ✓ can these by async, one div hidden another opened?
    - ✓ move emails section to after scan section in the menu
    - ✓ make menu items full buttons via css
      - ✓ 3d standing out unless its selected, then sunken
      - ✓ light purple colouring
        - ✓ is it possible to fade slightly lighter, via gradient, and back
        - ✓ put the gradient at a 75 degree angle from x axis, approx 24px in from the left (try and i will advise if its needs changing with more lines)

    - ✓ Emails
      - ✓ filters: account, tag (or no tag), search subject / sender
      - ✓ list: received, account, from, subject, tags - 100 per page, newer / older buttons
      - ✓ click an email: from, to, cc, sent on, received, folder, attachments, body
      - ✓ tags on the email
        - ✓ dashed = set by the scan: ✓ keep it, × not this tag (the scan will not add it again)
        - ✓ filled = yours: × remove
        - ✓ struck through = rejected: ↺ undo
        - ✓ add a tag from the list
      - ✓ open in outlook button (outlook marks the email as read)
      - ✓ tag again button
      - ✓ default show the filters, do not show emails
      - ✓ have a div for summary
        - ✓ choose from the last two weeks
        - ✓ list all those scans in a combo
        - ✓ on select
          - ✓ render the information in an async div within the div for summary
            - ✓ max height 400px
            - ✓ scrollable

    - ✓ Scan
      - ✓ pick mailboxes (from config/settings.json), days back, tag the new emails
      - ✓ scan now
      - ✓ tag untagged emails
      - ✓ log of the scans
        - ✓ allow collaspable
      - button --> clear log
        - bin icon


  - Settings
    - use a cog icon in a button
    - right align the button
    - sub menu item of the Tags
      - ✓ Tags
        - ✓ edit tag, description, sender patterns, subject keywords, order, active
        - ✓ add a tag
        - ✓ number of emails per tag
        - ✓ only problem I had was swapping to the other tab and back lost the entered yet not saved details. async should fix that
        - ✓ option to cancel and remove the line not yet saved
        - ✓ colour the saved lines in very light green
        - ✓ and adjustments/dirtying the row, change to orange, inclduing the new row.
        - ✓ have a second add tag button at the top -> jumps to the bottom and creates like the current button does


- Actions
  - ✓ email scanner (scan.py)
    - ✓ mailboxes: vincent@massarius.com, Massarius | Billing, Massarius | Finance - read only
    - ✓ inbox with its sub folders + sent items, last x days
    - ✓ my_sql cms_db
      - ✓ emails: account, from, to, cc, sent on, received, subject, body, attachments, folder, outlook link
      - ✓ lookup_tags: internal, ssp, client, dashboard, invoice, newsletter + their rules
      - ✓ email_tags: auto (the scan's) / manual (yours) / rejected
    - ✓ emails already stored are refreshed, their tags are kept
    - ✓ auto tagging: rules first, then anything llm (qwen, local)
    - ✓ open an email from a link: http://127.0.0.1:8770/open/<id>
    - ✓ scheduled task "CMS Massarius scan": 09:00 and 17:00, 1 day back
    - ✓ python scan.py --retag untagged (or all): tag again without reading outlook
    - ✓ on scan
      - ✓ produce a summary of the last run (usually day)
        - ✓ hold in a table - scan info
          - ✓ scan date/time
          - ✓ filters (number of days etc)
        - ✓ hold in a table - scan details
          - ✓ summary line(s)/row(s)
        - ✓ not sure how yet, but flag those that sound important to appear in the summary
          - ✓ experiment with anything llm and a request may be.. not too important yet
        - catch any errors
          - summarise the error
            - collapse the error details - clickable to open and see
            - highlight in red on the log
          - suggest action(s) to clear up
            - if mysql isnt runnging - suggest running
            - if outlook library is erroring, etc

    - when scanning, next to log collapsable text -> add an css that is spinning balls that change through the rainbox colours as they circle. 
      - hide once complete
      - auto swap to emails tab
  - Scan -> clear log button
    - clears the div with the log information
