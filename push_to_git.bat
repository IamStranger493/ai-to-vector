@echo off
cd /d "%~dp0"
setlocal enabledelayedexpansion

title Vectorizer Studio - Git Push Utility
echo ======================================================
echo       AI-to-Vector: Push Project to GitHub / Git
echo ======================================================
echo.

REM 1. Check if Git is installed
where git >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Git is not installed or not in system PATH.
    echo Please install Git from https://git-scm.com/
    goto :pause_end
)

REM 2. Check if this is a Git repository
if not exist ".git" (
    echo [INFO] Initializing new Git repository...
    git init
    git branch -M main
)

REM 3. Check Git Remote
git remote get-url origin >nul 2>nul
if errorlevel 1 goto :ask_remote
goto :show_remote

:ask_remote
echo [NOTICE] No remote repository (origin) is configured yet.
echo.
echo Please enter your GitHub / Git Repository URL:
echo (Example: https://github.com/your-username/ai-to-vector.git)
set "REPO_URL="
set /p REPO_URL="Repository URL: "
if "!REPO_URL!"=="" (
    echo.
    echo [ERROR] Repository URL cannot be empty.
    goto :pause_end
)
git remote add origin !REPO_URL!
echo [SUCCESS] Remote origin added: !REPO_URL!
echo.
goto :stage_files

:show_remote
for /f "tokens=*" %%i in ('git remote get-url origin') do set CURRENT_REMOTE=%%i
echo [INFO] Current Remote: %CURRENT_REMOTE%
echo.

:stage_files
echo [INFO] Current git status:
git status -s
echo.
echo [INFO] Staging all changes...
git add .
echo.

set COMMIT_MSG=
set /p COMMIT_MSG="Enter commit message (Press Enter for default: 'Update vectorizer project'): "
if "%COMMIT_MSG%"=="" set COMMIT_MSG=Update vectorizer project

git commit -m "%COMMIT_MSG%"

echo.
echo [INFO] Pushing changes to remote main branch...
git branch -M main
git push -u origin main

if errorlevel 1 (
    echo.
    echo ======================================================
    echo   [FAILED] Push failed. If the remote repository has
    echo   existing commits, you may need to pull first:
    echo   Run: git pull origin main --rebase
    echo ======================================================
) else (
    echo.
    echo ======================================================
    echo   [SUCCESS] Code successfully pushed to Git!
    echo ======================================================
)

:pause_end
echo.
echo Press any key to close this window...
pause >nul
