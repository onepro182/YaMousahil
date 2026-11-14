# YaMousahil — Alerte d'adhan en arrière-plan pour Windows
# Fonctionne MEME SI le navigateur (Chrome/Edge) est ferme et meme si la session est verrouillee.
# Idee : une tache planifiee (Task Scheduler) execute ce script chaque minute ;
#        le script recupere les horaires du jour (cache local) et affiche un toast Windows + joue l'adhan.
#
# Usage :
#   powershell -ExecutionPolicy Bypass -File adhan-windows.ps1 -Action Test       # toast + adhan maintenant
#   powershell -ExecutionPolicy Bypass -File adhan-windows.ps1 -Action Install    # enregistre la tache (toutes les minutes)
#   powershell -ExecutionPolicy Bypass -File adhan-windows.ps1 -Action Check      # ce que la tache execute
#   powershell -ExecutionPolicy Bypass -File adhan-windows.ps1 -Action Uninstall  # supprime la tache
#   powershell -ExecutionPolicy Bypass -File adhan-windows.ps1 -Action ShowTimes  # affiche les horaires du jour
#
# 2e PC Windows : copier le dossier du projet (APP_web) dessus, puis -Action Install avec le meme chemin.

param(
    [ValidateSet('Check','Test','Install','Uninstall','ShowTimes')]
    [string]$Action = 'Check',

    # ===== Configuration (ville par defaut : Oujda, Maroc — methode = Habous) =====
    [string]$City            = 'Oujda',
    [string]$Country         = 'Morocco',
    [int]   $Method          = 21,     # 21 = Maroc (Ministere des Habous et des Affaires Islamiques)
    [int]   $ReminderMinutes = 10,     # rappel N minutes avant l'adhan (0 = desactive)
    [switch]$NoAdhan,                  # desactive l'adhan sonore
    [switch]$NoReminder,               # desactive le rappel
    [string]$AppDir          = (Split-Path -Parent $PSScriptRoot),  # racine du projet (contient Logo.png + assets\audio)
    [int]   $TestSoundSeconds = 25,    # duree max de lecture pendant -Action Test
    [int]   $FullAdhanSeconds = 240    # duree max de lecture a l'heure de l'adhan
)

$ErrorActionPreference = 'Stop'
$CacheDir   = Join-Path $env:LOCALAPPDATA 'YaMousahil'
$StateDir   = $CacheDir
$AdhanFile  = Join-Path $AppDir 'assets\audio\adhan-azan1.mp3'
$LogoFile   = Join-Path $AppDir 'Logo.png'
$TaskName   = 'YaMousahil-Adhan'

$prayerAr = @{ Fajr='الفجر'; Sunrise='الشروق'; Dhuhr='الظهر'; Asr='العصر'; Maghrib='المغرب'; Isha='العشاء' }
$prayerFr = @{ Fajr='Fajr'; Dhuhr='Dhuhr'; Asr='Asr'; Maghrib='Maghrib'; Isha='Isha' }
$order    = @('Fajr','Dhuhr','Asr','Maghrib','Isha')

function Ensure-Dir { param([string]$Path) if (-not (Test-Path $Path)) { New-Item -ItemType Directory -Force -Path $Path | Out-Null } }

# Heure locale Maroc independante du fuseau Windows (Windows affiche souvent GMT sur cette machine,
# alors que les horaires aladhan sont en heure du Maroc).
# Regle officielle Maroc (comme l'app) : UTC+1 toute l'annee, SAUF pendant le Ramadan -> UTC+0.
function Get-MoroccoOffsetMinutes {
    param([datetime]$Date)
    $y = $Date.Year
    $day = $Date.Date
    $lastSunday = {
        param([int]$month)   # month 0-based (1 = fevrier, 2 = mars)
        $d = [datetime]::new($y, $month + 1, 1)
        $d = $d.AddMonths(1).AddDays(-1)          # dernier jour du mois
        while ($d.DayOfWeek -ne 'Sunday') { $d = $d.AddDays(-1) }
        return $d
    }
    $start = & $lastSunday 1   # dernier dimanche de fevrier : passage a GMT+0
    $end   = & $lastSunday 2   # dernier dimanche de mars    : retour a GMT+1
    if ($day -ge $start -and $day -lt $end) { return 0 }
    return 60
}

function Get-NowMorocco { (Get-Date).ToUniversalTime().AddMinutes((Get-MoroccoOffsetMinutes (Get-Date))) }

function Get-CachePath {
    param([string]$Prefix)
    $d = (Get-NowMorocco).ToString('yyyy-MM-dd')
    Join-Path $CacheDir "$Prefix-$d.json"
}

function Get-PrayerTimes {
    # Cache local du jour
    $cache = Get-CachePath 'timings'
    if (Test-Path $cache) {
        try { return (Get-Content $cache -Raw | ConvertFrom-Json) } catch { }
    }
    Ensure-Dir $CacheDir
    $city    = [uri]::EscapeDataString($City)
    $country = [uri]::EscapeDataString($Country)
    $url = "https://api.aladhan.com/v1/timingsByCity?city=$city&country=$country&method=$Method"
    try {
        $resp = Invoke-RestMethod -Uri $url -TimeoutSec 12
        if ($resp.code -ne 200 -or -not $resp.data.timings) { throw "reponse API invalide" }
        $t = $resp.data.timings
        $times = [ordered]@{}
        foreach ($k in $order) {
            $raw = [string]$t.$k
            $times[$k] = $raw.Substring(0, [Math]::Min(5, $raw.Length))  # "HH:mm"
        }
        $obj = [PSCustomObject]@{ City=$City; Method=$Method; Date=(Get-NowMorocco).ToString('yyyy-MM-dd'); Times=[PSCustomObject]$times }
        $obj | ConvertTo-Json -Compress | Out-File -FilePath $cache -Encoding ascii
        return $obj
    } catch {
        # Hors ligne : retomber sur le cache d'hier s'il existe
        $yesterday = (Get-NowMorocco).AddDays(-1).ToString('yyyy-MM-dd')
        $old = Join-Path $CacheDir "timings-$yesterday.json"
        if (Test-Path $old) {
            Write-Host "Hors ligne — reutilisation des horaires d'hier ($old)"
            return (Get-Content $old -Raw | ConvertFrom-Json)
        }
        throw "Impossible de recuperer les horaires ($($_.Exception.Message)) et aucun cache disponible."
    }
}

function Get-PrayerDateTime {
    param([PSCustomObject]$Times, [string]$Key)
    $hm = $Times.$Key
    $parts = $hm.Split(':')
    $dt = (Get-NowMorocco).Date
    return $dt.AddHours([int]$parts[0]).AddMinutes([int]$parts[1])
}

function Load-Sent {
    $f = Get-CachePath 'sent'
    if (Test-Path $f) { try { return @(Get-Content $f -Raw | ConvertFrom-Json) } catch { return @() } }
    return @()
}

function Save-Sent {
    param([string[]]$Items)
    Ensure-Dir $StateDir
    $f = Get-CachePath 'sent'
    $Items | ConvertTo-Json -Compress | Out-File -FilePath $f -Encoding ascii
}

function Show-Toast {
    param([string]$Title, [string]$Body, [switch]$Silent)
    try {
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
        $logo = $LogoFile -replace '\\','/'
        $audio = if ($Silent) { "<audio silent='true'/>" } else { "<audio src='ms-winsoundevent:Notification.Looping.Alarm' loop='false'/>" }
        $img = if (Test-Path $LogoFile) { "<image placement='appLogoOverride' src='file:///$logo'/>" } else { '' }
        $xmlStr = "<toast><visual><binding template='ToastGeneric'>$img<text>$Title</text><text>$Body</text></binding></visual>$audio</toast>"
        $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        $xml.LoadXml($xmlStr)
        $toast = New-Object Windows.UI.Notifications.ToastNotification $xml
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('YaMousahil').Show($toast)
        Write-Host "Toast envoye : $Title — $Body"
    } catch {
        Write-Warning "Toast impossible : $($_.Exception.Message)"
    }
}

function Start-AdhanAudio {
    param([int]$Seconds = 240)
    if (-not (Test-Path $AdhanFile)) {
        Write-Warning "Fichier adhan introuvable : $AdhanFile — son par defaut joue."
        [System.Media.SystemSounds]::Exclamation.Play() | Out-Null
        return
    }
    # Processus enfant cache pour ne pas bloquer la tache planifiee ni la boucle
    $adhanEsc = $AdhanFile -replace "'", "''"
    $child = "`$w=New-Object -ComObject 'WMPlayer.OCX';`$w.URL='$adhanEsc';`$w.Controls.Play();Start-Sleep -Seconds $Seconds;`$w.Controls.Stop();`$w.Close()"
    Start-Process -FilePath 'powershell.exe' -WindowStyle Hidden -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-Command',$child | Out-Null
    Write-Host "Adhan en lecture ($AdhanFile)"
}

function Invoke-Check {
    param([switch]$WhatIf)
    $data = Get-PrayerTimes
    $sent = @(Load-Sent)
    $now  = Get-NowMorocco
    Write-Host "Verification $(Get-Date -Format 'HH:mm:ss') — heure Maroc $($now.ToString('HH:mm:ss')) — $City (methode $Method)"
    foreach ($p in $order) {
        $at = Get-PrayerDateTime -Times $data.Times -Key $p
        $nameAr = $prayerAr[$p]; $nameFr = $prayerFr[$p]

        # Rappel N minutes avant
        if (-not $NoReminder -and $ReminderMinutes -gt 0) {
            $remAt = $at.AddMinutes(-$ReminderMinutes)
            if ($now -ge $remAt -and $now -lt $remAt.AddMinutes(2) -and ($sent -notcontains "$($data.Date)_rem_$p")) {
                Write-Host "Rappel du $nameFr (dans $ReminderMinutes min)"
                if (-not $WhatIf) {
                    Show-Toast -Title "اقترب موعد صلاة $nameAr" -Body "باقي $ReminderMinutes دقائق على صلاة $nameAr"
                    $sent += "$($data.Date)_rem_$p"; Save-Sent $sent
                }
            }
        }
        # Adhan a l'heure de la priere
        if (-not $NoAdhan) {
            if ($now -ge $at -and $now -lt $at.AddMinutes(5) -and ($sent -notcontains "$($data.Date)_adhan_$p")) {
                Write-Host "ADHAN du $nameFr !"
                if (-not $WhatIf) {
                    Show-Toast -Title "حان الآن موعد صلاة $nameAr" -Body "ارفع الأذان الآن"
                    Start-AdhanAudio -Seconds $FullAdhanSeconds
                    $sent += "$($data.Date)_adhan_$p"; Save-Sent $sent
                }
            }
        }
    }
}

switch ($Action) {
    'ShowTimes' {
        $data = Get-PrayerTimes
        Write-Host "Horaires du $($data.Date) — $($data.City) (methode $($data.Method)) :"
        Write-Host "Maintenant (heure du Maroc) : $((Get-NowMorocco).ToString('HH:mm:ss'))"
        foreach ($p in $order) {
            $at = Get-PrayerDateTime -Times $data.Times -Key $p
            Write-Host ("  {0,-8} {1}   ({2})" -f $prayerFr[$p], $data.Times.$p, $prayerAr[$p])
        }
    }
    'Check' { Invoke-Check }
    'Test' {
        Show-Toast -Title "حان الآن موعد صلاة العشاء" -Body "إشعار تجريبي للأذان — YaMousahil"
        Start-AdhanAudio -Seconds $TestSoundSeconds
    }
    'Install' {
        $scriptPath = $MyInvocation.MyCommand.Path
        $psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $start = (Get-Date).AddMinutes(1).ToString('yyyy-MM-ddTHH:mm:sszzz')
        # Tache creee via XML : TOURNE SUR BATTERIE (sinon Windows ne lance jamais la tache)
        $args = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File &quot;$scriptPath&quot; -Action Check -City $City -Country $Country -Method $Method -ReminderMinutes $ReminderMinutes"
        $user = "$env:USERNAME"
        $xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>YaMousahil - alerte adhan chaque minute (toast + adhan, sans navigateur)</Description>
    <URI>\$TaskName</URI>
  </RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <StartBoundary>$start</StartBoundary>
      <Repetition><Interval>PT1M</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>
      <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT10M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <AllowStartOnDemand>true</AllowStartOnDemand>
  </Settings>
  <Principals>
    <Principal id="Author">
      <UserId>$user</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Actions Context="Author">
    <Exec>
      <Command>$psExe</Command>
      <Arguments>$args</Arguments>
    </Exec>
  </Actions>
</Task>
"@
        $xmlFile = Join-Path $env:TEMP ("yaMousahil-adhan-" + [guid]::NewGuid().ToString('N') + '.xml')
        [IO.File]::WriteAllText($xmlFile, $xml, (New-Object Text.UnicodeEncoding($false, $true)))
        & schtasks.exe /create /tn $TaskName /xml $xmlFile /f | Out-Null
        $code = $LASTEXITCODE
        Remove-Item $xmlFile -Force -ErrorAction SilentlyContinue
        if ($code -ne 0) { throw "schtasks a echoue (code $code)" }
        Ensure-Dir $CacheDir
        Write-Host "Tache '$TaskName' enregistree via XML (toutes les minutes, session ouverte, batterie OK)."
        Write-Host "Test immediate : -Action Test"
        # Pre-charge le cache pour aujourd'hui
        try { $null = Get-PrayerTimes; Write-Host "Horaires du jour charges en cache." } catch { Write-Warning $_ }
    }
    'Uninstall' {
        & schtasks.exe /delete /tn $TaskName /f | Out-Null
        Write-Host "Tache '$TaskName' supprimee (le cache local reste dans $CacheDir)."
    }
}
