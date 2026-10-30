; Stable AppId, executable and shortcut names are the upgrade contract.
#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef AppBinary
  #error AppBinary is required
#endif
#ifndef OutputPath
  #error OutputPath is required
#endif
#ifndef IconFile
  #error IconFile is required
#endif

[Setup]
AppId=com.seeutoken.desktop
AppName=seeUtoken
AppVersion={#AppVersion}
AppPublisher=seeUtoken
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\seeUtoken
UsePreviousAppDir=yes
DisableDirPage=yes
DefaultGroupName=seeUtoken
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputPath}
OutputBaseFilename=seeUtoken-V{#AppVersion}
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\seeUtoken.exe
Compression=lzma2
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
#if FileExists(CompilerPath + "\Languages\ChineseSimplified.isl")
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
#endif

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#AppBinary}"; DestName: "seeUtoken-upgrade.exe"; Flags: dontcopy
Source: "{#AppBinary}"; DestDir: "{app}"; DestName: "seeUtoken.exe"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\seeUtoken"; Filename: "{app}\seeUtoken.exe"; AppUserModelID: "seeUtoken.Desktop"
Name: "{autodesktop}\seeUtoken"; Filename: "{app}\seeUtoken.exe"; Tasks: desktopicon; AppUserModelID: "seeUtoken.Desktop"

[Run]
Filename: "{app}\seeUtoken.exe"; Description: "Launch seeUtoken"; Flags: nowait postinstall skipifsilent

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ExitCode: Integer;
begin
  Result := '';
  ExtractTemporaryFile('seeUtoken-upgrade.exe');
  if not Exec(ExpandConstant('{tmp}\seeUtoken-upgrade.exe'),
      '--prepare-upgrade "' + ExpandConstant('{tmp}\upgrade.json') + '"',
      '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then
    Result := 'Unable to prepare the upgrade. The existing installation has not been changed.'
  else if (ExitCode <> 0) or CheckForMutexes('Local\seeUtoken.Desktop') then
    Result := 'Please quit seeUtoken, then retry. The existing installation has not been changed.';
end;

function InitializeUninstall: Boolean;
var
  ExitCode: Integer;
begin
  Result := True;
  if CheckForMutexes('Local\seeUtoken.Desktop') then begin
    Result := Exec(ExpandConstant('{app}\seeUtoken.exe'),
      '--prepare-upgrade "' + ExpandConstant('{tmp}\upgrade.json') + '"',
      '', SW_HIDE, ewWaitUntilTerminated, ExitCode);
    Result := Result and (ExitCode = 0) and not CheckForMutexes('Local\seeUtoken.Desktop');
    if not Result then MsgBox('Please quit seeUtoken before uninstalling.', mbError, MB_OK);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Found: TFindRec;
  LegacyFile: String;
begin
  if CurStep = ssPostInstall then begin
    { Only remove version-named executables inside our managed installation. }
    if FindFirst(ExpandConstant('{app}\seeUtoken-V*.exe'), Found) then begin
      try
        repeat
          LegacyFile := ExpandConstant('{app}\') + Found.Name;
          if (Found.Attributes and FILE_ATTRIBUTE_DIRECTORY) = 0 then
            DeleteFile(LegacyFile);
        until not FindNext(Found);
      finally
        FindClose(Found);
      end;
    end;
  end;
end;
