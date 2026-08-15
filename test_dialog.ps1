Add-Type -AssemblyName System.Windows.Forms
$top = New-Object System.Windows.Forms.Form
$top.TopMost = $true
$top.ShowInTaskbar = $false
$top.WindowState = 'Minimized'
$top.Show()
$top.Activate()
$f = New-Object System.Windows.Forms.OpenFileDialog
$f.Title = 'Test File Dialog'
$res = $f.ShowDialog($top)
if ($res -eq [System.Windows.Forms.DialogResult]::OK) {
    Write-Output $f.FileName
}
$top.Dispose()
