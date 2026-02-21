AVVIARE DUE TERMINALE I DIFFERENTI DA POWERSHEL


🔷 STEP A — Attiva la venv PER IL BACKEND


cd D:\Python\FP_Other\FPFood

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1

poi dop fai

.\.venv\Scripts\python.exe -m uvicorn api.fpfood:app --reload --host 0.0.0.0 --port 8000



✅ 2) AVVIO FRONTEND (http.server)

cd D:\Python\FP_Other\FPFood\web

python.exe -m http.server 5000

http://localhost:5000/index.html





select codice,Descriz,SourceCode,QtaPrelDaMagaz,ModoPrelDaMagaz from inventariovoci where IdInv = 34 and qtaunit <> QtaPrelDaMagaz and qtapreldamagaz <>-1




online 

per aggiornare GitHub e rendere fai

cd D:\Python\FP_Other\FPFood

git add .
git commit -m "update"
git push
 