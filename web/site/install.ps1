# Orbit – instalace jedním příkazem (PowerShell):
#
#     irm https://orbit.easya.cz/install.ps1 | iex
#
# Stáhne nejnovější instalátor Orbitu z orbit.easya.cz, ověří jeho kontrolní součet SHA-256 proti
# download/latest.json a nainstaluje Orbit jen pro tebe (do %LOCALAPPDATA%\Programs\Orbit, bez práv správce).
# Pak Orbit spustí a průvodce tě provede nastavením. Zdrojový kód: https://github.com/josefkotran/orbit
& {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'   # the progress bar of PowerShell 5.1 slows big downloads a lot
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    if (-not [Environment]::Is64BitOperatingSystem -or [Environment]::OSVersion.Version.Build -lt 17763) {
        Write-Host 'Orbit potřebuje 64bitová Windows 10 (verze 1809 nebo novější) nebo Windows 11.' -ForegroundColor Red
        return
    }

    $base = 'https://orbit.easya.cz/download/'
    try { $release = Invoke-RestMethod ($base + 'latest.json') -UseBasicParsing }
    catch {
        Write-Host 'Instalátor zatím není ke stažení, nebo je web nedostupný. Zkus to později na https://orbit.easya.cz' -ForegroundColor Red
        return
    }

    $file = Join-Path $env:TEMP $release.file
    Write-Host ("Stahuji Orbit {0} ({1} MB)…" -f $release.version, [math]::Round($release.size / 1MB))
    Invoke-WebRequest ($base + $release.file) -OutFile $file -UseBasicParsing
    $hash = (Get-FileHash $file -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -ne $release.sha256.ToLowerInvariant()) {
        Remove-Item $file -Force -ErrorAction SilentlyContinue
        Write-Host 'Kontrolní součet nesedí, stažený soubor je poškozený. Nic jsem neinstaloval, zkus to znovu.' -ForegroundColor Red
        return
    }
    Write-Host 'Kontrolní součet sedí.'
    if ($env:ORBIT_INSTALL_DRYRUN) { Write-Host "Zkouška nanečisto: instalátor je v $file, neinstaluji."; return }

    Write-Host 'Instaluji…'
    $setup = Start-Process $file -ArgumentList '/SILENT', '/CURRENTUSER', '/SUPPRESSMSGBOXES', '/NORESTART' -Wait -PassThru
    Remove-Item $file -Force -ErrorAction SilentlyContinue
    if ($setup.ExitCode -ne 0) {
        Write-Host ("Instalace se nepovedla (kód {0}). Když Orbit běží, ukonči ho (pravým tlačítkem na jeho ikonu, Ukončit) a spusť příkaz znovu." -f $setup.ExitCode) -ForegroundColor Red
        return
    }

    $dir = Join-Path $env:LOCALAPPDATA 'Programs\Orbit'
    Start-Process (Join-Path $dir 'runtime\pythonw.exe') -ArgumentList '-s', ('"{0}"' -f (Join-Path $dir 'Orbit.pyw')) -WorkingDirectory $dir
    Write-Host 'Hotovo. Orbit se spouští a průvodce tě provede nastavením: jméno, mikrofon, klávesa, model a připojení Clauda.' -ForegroundColor Green
    Write-Host 'Pak stačí podržet zvolenou klávesu, mluvit a pustit.'
}
