[CmdletBinding()]
param(
    [string]$ConfigPath = "$HOME\.claude.json"
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    throw "Claude user configuration not found: $ConfigPath"
}

$secureToken = Read-Host 'PixelLab API token (input is hidden)' -AsSecureString
$tokenPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
$token = $null

try {
    $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPointer)
    if ([string]::IsNullOrWhiteSpace($token)) {
        throw 'PixelLab API token cannot be blank.'
    }
    if ($token.Length -lt 16) {
        throw "PixelLab API token is unexpectedly short ($($token.Length) character(s)). Paste the complete token from the PixelLab account page."
    }
    if ($token -match '\s' -or $token -match '[\x00-\x1F\x7F]') {
        throw 'PixelLab API token contains whitespace or control characters. Paste only the token value, without the command or Bearer prefix.'
    }

    $configuration = Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json
    if (-not $configuration.mcpServers) {
        $configuration | Add-Member -MemberType NoteProperty -Name mcpServers -Value ([pscustomobject]@{})
    }

    $server = $configuration.mcpServers.pixellab
    if (-not $server) {
        $server = [pscustomobject]@{
            type = 'http'
            url = 'https://api.pixellab.ai/mcp'
        }
        $configuration.mcpServers | Add-Member -MemberType NoteProperty -Name pixellab -Value $server
    }

    $server.type = 'http'
    $server.url = 'https://api.pixellab.ai/mcp'
    if (-not $server.headers) {
        $server | Add-Member -MemberType NoteProperty -Name headers -Value ([pscustomobject]@{})
    }
    if ($server.headers.PSObject.Properties.Name -contains 'Authorization') {
        $server.headers.Authorization = "Bearer $token"
    }
    else {
        $server.headers | Add-Member -MemberType NoteProperty -Name Authorization -Value "Bearer $token"
    }

    $backupPath = "$ConfigPath.pixellab-backup"
    Copy-Item -LiteralPath $ConfigPath -Destination $backupPath -Force

    $temporaryPath = "$ConfigPath.pixellab-new"
    $json = $configuration | ConvertTo-Json -Depth 100
    [IO.File]::WriteAllText($temporaryPath, $json, [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporaryPath -Destination $ConfigPath -Force

    $verified = Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json
    if ($verified.mcpServers.pixellab.headers.Authorization -notmatch '^Bearer\s+\S+$') {
        throw "PixelLab MCP configuration verification failed. Restore $backupPath."
    }

    Write-Host 'PixelLab MCP authorization configured. The token was not printed.'
    Write-Host "Backup: $backupPath"
}
finally {
    if ($tokenPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPointer)
    }
    $token = $null
    $secureToken = $null
}
