@echo off
REM ============================================================
REM  NEW RUN - one click = one fresh randomized Nuzlocke world
REM  Place in the hg-engine repo root (next to docker-makerom.cmd)
REM  Usage:  new_run.cmd                 (solo, random seed)
REM          new_run.cmd 12345           (solo, specific seed)
REM          new_run.cmd 12345 A         (Soul Link, Player A)
REM          new_run.cmd 12345 B         (Soul Link, Player B)
REM  Soul Link partners must agree on a seed and each run this
REM  on their own machine with their own legally dumped rom.nds.
REM ============================================================
setlocal
set SEED=%1
if "%SEED%"=="" set /a SEED=%RANDOM% * 32768 + %RANDOM%
set LINK=%2
set EXTRA=
set SUFFIX=
if not "%LINK%"=="" set EXTRA=--soul-link %LINK%
if not "%LINK%"=="" set SUFFIX=_player%LINK%

echo.
echo === New run, seed %SEED% %LINK% ===
echo.

git checkout -- data/Encounters.c data/Trainers.c src/starters.c
if errorlevel 1 ( echo Could not reset data files - is this the repo root? & exit /b 1 )

python tools\johto_randomizer.py --seed %SEED% %EXTRA%
if errorlevel 1 ( echo Randomizer failed - see message above. & exit /b 1 )

call docker-makerom.cmd
if errorlevel 1 ( echo Build failed - see message above. & exit /b 1 )

if not exist runs mkdir runs
copy /Y test.nds "runs\johto_seed_%SEED%%SUFFIX%.nds" >nul
if exist randomizer_spoiler_log.txt copy /Y randomizer_spoiler_log.txt "runs\johto_seed_%SEED%%SUFFIX%_SPOILERS.txt" >nul
if exist soul_link_pairs.txt copy /Y soul_link_pairs.txt "runs\johto_seed_%SEED%_PAIRS.txt" >nul

echo.
echo ============================================================
echo  Your world is ready:  runs\johto_seed_%SEED%%SUFFIX%.nds
echo  Load it in your emulator and pick New Game. Good luck!
echo ============================================================
endlocal
