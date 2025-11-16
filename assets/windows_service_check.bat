@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
color 0A

set "Services=SysMain Dnscache DusmSvc WinDefend DPS PcaSvc Appinfo BFE mpssvc EventLog DiagTrack CDPSvc Bam"
set "allActive=true"
set "inactiveServices="

REM ========================== HEADER ==========================
echo(
echo ╔════════════════════════════════════════════════════════════════╗
echo ║                    Service Status Analysis (Windows)           ║
echo ╚════════════════════════════════════════════════════════════════╝
echo(
echo ╔════════════════════════════╦════════════════════════════╗
echo ║          Service           ║           Status           ║
echo ╠════════════════════════════╬════════════════════════════╣

for %%S in (%Services%) do (
    set "sp=                         "
    set "svc=%%S!sp!"
    set "svc=!svc:~0,26!"

    sc query "%%S" | find "RUNNING" >nul
    if errorlevel 1 (
        echo ║ !svc! ║          INACTIVE          ║
        set "allActive=false"
        set "inactiveServices=!inactiveServices! %%S"
    ) else (
        echo ║ !svc! ║           ACTIVE           ║
    )
)

echo ╚════════════════════════════╩════════════════════════════╝

REM ========================== STATUS BLOCK ==========================
if "!allActive!"=="true" (
    echo(
    echo ╔════════════════════════════════════════════════════════════════╗
    echo ║                All listed services are ACTIVE.                 ║
    echo ╚════════════════════════════════════════════════════════════════╝
) else (
    echo(
    echo ╔════════════════════════════════════════════════════════════════╗
    echo ║             Some services are currently INACTIVE.              ║
    echo ╚════════════════════════════════════════════════════════════════╝
    echo The following services are inactive:
    for %%S in (!inactiveServices!) do (
        echo   - %%S
    )
    echo(
    echo Do you want to activate all inactive services now? {Y/N}
    set /p "answer=> "
    if /I "!answer!"=="Y" (
        echo(
        echo ╔════════════════════════════════════════════════════════════════╗
        echo ║             Starting inactive services...                      ║
        echo ╚════════════════════════════════════════════════════════════════╝
        for %%S in (!inactiveServices!) do (
            sc config "%%S" start= auto >nul
            net start "%%S" >nul
        )
        echo(
        echo         [ OK ] All inactive services have been started.
    ) else (
        echo(
        echo         [INFO] Inactive services were not started.
    )
)

REM ========================== TPM & SECURE BOOT ==========================
echo(
echo ╔════════════════════════════════════════════════════════════════╗
echo ║              Checking TPM Status and Secure Boot               ║
echo ╚════════════════════════════════════════════════════════════════╝
echo(

powershell -Command "Get-Tpm | Select-Object -ExpandProperty TpmPresent" > tpm_status.txt
set /p "tpmStatus="<tpm_status.txt
del tpm_status.txt

powershell -Command "Confirm-SecureBootUEFI" > secure_boot_status.txt
set /p "secureBootStatus="<secure_boot_status.txt
del secure_boot_status.txt

echo ╔════════════════════════════╦════════════════════════════╗
echo ║          Feature           ║           Status           ║
echo ╠════════════════════════════╬════════════════════════════╣

set "feature=TPM                     "
set "feature=!feature:~0,26!"
if "%tpmStatus%"=="True" (
    echo ║ !feature!   ║           ENABLED          ║
) else (
    echo ║ !feature!   ║           DISABLED         ║
)

set "feature=Secure Boot             "
set "feature=!feature:~0,26!"
if "%secureBootStatus%"=="True" (
    echo ║ !feature!   ║           ENABLED          ║
) else (
    echo ║ !feature!   ║           DISABLED         ║
)

echo ╚════════════════════════════╩════════════════════════════╝

REM ========================== FOOTER ==========================
echo(
echo ╔════════════════════════════════════════════════════════════════╗
echo ║                      System Check Completed                    ║
echo ╚════════════════════════════════════════════════════════════════╝
echo(
pause