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

    # with Orbit running the installer gives up, so say it before downloading 80 MB (the dry run installs nothing)
    if (-not $env:ORBIT_INSTALL_DRYRUN) {
        $m = $null; $running = $false
        try { $running = [Threading.Mutex]::TryOpenExisting('Local\Orbit-single-instance', [ref]$m) }
        catch [UnauthorizedAccessException] { $running = $true }   # it exists, it is just not ours to open
        if ($running) {
            if ($m) { $m.Dispose() }
            Write-Host 'Orbit právě běží. Ukonči ho (pravým tlačítkem na jeho ikonu u hodin, Ukončit) a spusť příkaz znovu.' -ForegroundColor Yellow
            return
        }
    }

    $base = 'https://orbit.easya.cz/download/'
    try { $release = Invoke-RestMethod ($base + 'latest.json') -UseBasicParsing }
    catch {
        Write-Host 'Instalátor zatím není ke stažení, nebo je web nedostupný. Zkus to později na https://orbit.easya.cz' -ForegroundColor Red
        return
    }
    # the name ends up in a path under %TEMP%, the hash is compared below: accept only what the page itself writes
    if ($release.file -notmatch '^Orbit-Setup-[\d.]+\.exe$' -or $release.sha256 -notmatch '^[0-9a-fA-F]{64}$' -or -not ($release.size -gt 0)) {
        Write-Host 'Popis instalátoru na webu je poškozený, nic jsem nestáhl. Zkus to později na https://orbit.easya.cz' -ForegroundColor Red
        return
    }

    $file = Join-Path $env:TEMP $release.file
    Write-Host ("Stahuji Orbit {0} ({1} MB)…" -f $release.version, [math]::Round($release.size / 1MB))
    try { Invoke-WebRequest ($base + $release.file) -OutFile $file -UseBasicParsing }
    catch {
        Remove-Item $file -Force -ErrorAction SilentlyContinue
        Write-Host 'Stažení se přerušilo nebo soubor na webu chybí. Zkontroluj připojení a zkus to znovu.' -ForegroundColor Red
        return
    }
    if ((Get-Item $file).Length -ne $release.size) {
        Remove-Item $file -Force -ErrorAction SilentlyContinue
        Write-Host 'Stažení se nedokončilo. Zkus to znovu.' -ForegroundColor Red
        return
    }
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
