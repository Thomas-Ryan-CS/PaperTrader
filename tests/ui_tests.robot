*** Settings ***
Library    SeleniumLibrary
Library    Process
Library    String

Suite Setup      Start PaperTrader Server
Suite Teardown   Stop PaperTrader Server

*** Variables ***
${PROJECT_ROOT}    C:/PaperTrader
${BASE_URL}        http://localhost:5000
${BROWSER}         Chrome
${PYTHON}          python      # change to full path to your venv python if needed

*** Keywords ***
Start PaperTrader Server
    [Documentation]   Start the Flask server as a background process.
    ${proc}=    Start Process    ${PYTHON}    app.py
    ...         cwd=${PROJECT_ROOT}
    ...         stdout=server.log
    ...         stderr=server_err.log
    ...         shell=True
    Set Suite Variable    ${SERVER_PROCESS}    ${proc}
    Sleep    5s    # give the server time to start

Stop PaperTrader Server
    [Documentation]   Stop the Flask server process started in Suite Setup.
    Terminate Process    ${SERVER_PROCESS}    kill=True

*** Test Cases ***

Signup Missing Fields Shows Error
    Open Browser    ${BASE_URL}/signup    ${BROWSER}
    Input Text      name=username    ${EMPTY}
    Input Text      name=password    ${EMPTY}
    # click submit button for the form
    Click Button    css:button[type="submit"]
    # be flexible on the exact message – just check the core text
    Wait Until Page Contains    Enter username    5s
    Close Browser

Signup Duplicate Username Shows Error
    ${username}=    Set Variable    robot_user

    # First signup
    Open Browser    ${BASE_URL}/signup    ${BROWSER}
    Input Text      name=username    ${username}
    Input Text      name=password    testpass
    Click Button    css:button[type="submit"]
    Wait Until Location Contains    /    5s
    Close Browser

    # Second signup with same username
    Open Browser    ${BASE_URL}/signup    ${BROWSER}
    Input Text      name=username    ${username}
    Input Text      name=password    anotherpass
    Click Button    css:button[type="submit"]
    Wait Until Page Contains    Username already taken    5s
    Close Browser

Login Invalid Credentials Shows Error
    Open Browser    ${BASE_URL}/login    ${BROWSER}
    Input Text      name=username    nosuchuser
    Input Text      name=password    wrongpass
    Click Button    css:button[type="submit"]
    Wait Until Page Contains    Invalid credentials    5s
    Close Browser

Signup And See Dashboard Tickers
    Open Browser    ${BASE_URL}/signup    ${BROWSER}
    ${random}=      Generate Random String    8
    ${username}=    Set Variable    rf_${random}
    Input Text      name=username    ${username}
    Input Text      name=password    testpass123
    Click Button    css:button[type="submit"]
    Wait Until Location Contains    /    5s
    Page Should Contain    AAPL
    Page Should Contain    MSFT
    Close Browser
