@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
set "YAKUZA_DISC_DIR=%~1"
if not defined YAKUZA_DISC_DIR (
  echo YakuzaRecomp - experimental PAL Windows test
  echo.
  echo Enter the folder containing all extracted PAL disc files.
  echo You can drag that folder into this window and press Enter.
  set /p "YAKUZA_DISC_DIR=Disc folder: "
)
set "YAKUZA_DISC_DIR=%YAKUZA_DISC_DIR:"=%"
> "%~dp0native-test.log" echo [launcher] checking extracted PAL disc files
set "YAKUZA_MISSING_DISC_FILES="
for %%F in (SYSTEM.CNF SLES_541.71 MAIN.BIN IRX.DAT IOPRP300.IMG PAL_NTSC.DAT OGRE.CVM OGRE2.CVM OGRE3.CVM OGRE4.CVM OGREDIR.BIN OGREDIR2.BIN OGREDIR3.BIN OGREDIR4.BIN) do (
  if not exist "%YAKUZA_DISC_DIR%\%%F" (
    echo Missing disc file: %%F
    >> "%~dp0native-test.log" echo [launcher] missing_file=%%F
    set "YAKUZA_MISSING_DISC_FILES=1"
  )
)
if defined YAKUZA_MISSING_DISC_FILES goto missing
if not exist "%~dp0YakuzaRecomp-test.exe" goto extract
set "YAKUZA_BOOT_DUMP_GS=1"
echo Starting the test. Press Escape or close the game window to exit.
echo Output is saved to native-test.log in this folder.
rem A final dot keeps a trailing directory backslash from escaping its quote.
"%~dp0YakuzaRecomp-test.exe" "%YAKUZA_DISC_DIR%\." 1800 "%~dp0diagnostics" continue > "%~dp0native-test.log" 2>&1
set "YAKUZA_TEST_EXIT_CODE=%ERRORLEVEL%"
> "%~dp0exit-code.txt" echo %YAKUZA_TEST_EXIT_CODE%
>> "%~dp0native-test.log" echo [launcher] exit_code=%YAKUZA_TEST_EXIT_CODE%
echo.
echo Test exit code: %YAKUZA_TEST_EXIT_CODE%
echo Open native-test.log for the result and any error.
if not defined YAKUZA_LAUNCHER_NO_PAUSE pause
exit /b %YAKUZA_TEST_EXIT_CODE%
:missing
echo.
echo Extract all files from your PAL ISO into one folder, including the CVM archives.
echo Keep the CVM archives intact. See the missing filenames above.
echo An ISO or ISO.GZ file by itself is not an extracted disc folder.
echo The missing-file list is also saved in native-test.log.
> "%~dp0exit-code.txt" echo 2
>> "%~dp0native-test.log" echo [launcher] exit_code=2
if not defined YAKUZA_LAUNCHER_NO_PAUSE pause
exit /b 2
:extract
echo Extract every file from the test ZIP into one folder first.
> "%~dp0exit-code.txt" echo 2
>> "%~dp0native-test.log" echo [launcher] missing_native_executable=YakuzaRecomp-test.exe
>> "%~dp0native-test.log" echo [launcher] exit_code=2
if not defined YAKUZA_LAUNCHER_NO_PAUSE pause
exit /b 2
