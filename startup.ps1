$ErrorActionPreference = 'Stop'

try {
    $lotsePvDir = "C:\ProgramData\Kubernetes\Lotse\lotse-pv"
    if (-not (Test-Path -Path $lotsePvDir)) {
        New-Item -ItemType Directory -Path $lotsePvDir -Force | Out-Null
    }

    Write-Host "Installing angular cli..." -ForegroundColor Cyan
    & npm install -g @angular/cli

    Push-Location -Path "lotse-ui"

    Write-Host "Installing npm packages..." -ForegroundColor Cyan
    & npm install

    if ($LASTEXITCODE -ne 0) { throw "npm install failed" }

    Write-Host "Building the project..." -ForegroundColor Cyan
    & ng build --base-href /lotse/ui/

    if ($LASTEXITCODE -ne 0) { throw "npm build failed" }

    Pop-Location

    Write-Host "Copying build files..." -ForegroundColor Cyan
    Copy-Item -Path "lotse-ui/dist/browser/*" -Destination "ui" -Recurse -Force

    Write-Host "Building Docker image..." -ForegroundColor Cyan
    & docker build -t lotse:v1 -f k8s.dockerfile .

    if ($LASTEXITCODE -ne 0) { throw "Docker build failed" }

    Write-Host "Installing NGINX ingress controller..." -ForegroundColor Cyan
    & kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.12.1/deploy/static/provider/cloud/deploy.yaml

    Write-Host "Waiting for NGINX ingress controller to be ready..." -ForegroundColor Cyan
    & kubectl wait --namespace ingress-nginx `
      --for=condition=ready pod `
      --selector=app.kubernetes.io/component=controller `
      --timeout=90s

    Write-Host "Patching NGINX configmap..." -ForegroundColor Cyan   
    & kubectl patch configmap ingress-nginx-controller -n ingress-nginx --patch '
data:
  allow-snippet-annotations: "true"
  annotations-risk-level: Critical'

    Write-Host "Install metrics server..." -ForegroundColor Cyan
    & kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

    Write-Host "Patching metric server..." -ForegroundColor Cyan
    & kubectl patch deployment metrics-server -n kube-system --type='json' -p='[{"op": "add", "path": "/spec/template/spec/containers/0/args/-", "value": "--kubelet-insecure-tls"}]'

    Write-Host "Creating Kubernetes namespace..." -ForegroundColor Cyan
    & kubectl create namespace lotse --dry-run=client -o yaml | kubectl apply -f -

    Write-Host "Applying Kubernetes configurations..." -ForegroundColor Cyan
    & kubectl apply -f k8s/kubeyaml/local-storage.yaml -n lotse
    & kubectl apply -f k8s/kubeyaml/k8s-auth.yaml -n lotse
    & kubectl apply -f k8s/kubeyaml/k8s-docker.yaml -n lotse
    
    Write-Host "Deployment completed successfully!" -ForegroundColor Green
} catch {
    Write-Error "An error occurred: $_"
    exit 1
}