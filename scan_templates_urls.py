"""
Script simplificado - gera arquivo resultado_scan.txt
"""

import re
from pathlib import Path

# Abrir arquivo de saída
output = open("resultado_scan.txt", "w", encoding="utf-8")

def log(msg):
    print(msg)
    output.write(msg + "\n")

log("=" * 70)
log("ESCANEANDO TEMPLATES HTML")
log("=" * 70)
log("")

templates_dir = Path("templates")

if not templates_dir.exists():
    log("ERRO: Pasta templates/ nao encontrada!")
    output.close()
    exit()

total_files = 0
total_issues = 0

for html_file in sorted(templates_dir.glob("admin_*.html")):
    total_files += 1
    
    log(f"Arquivo: {html_file.name}")
    log("-" * 70)
    
    try:
        content = html_file.read_text(encoding="utf-8")
        
        # Procurar fetch() URLs
        urls = re.findall(r'fetch\s*\([^)]*[\'"`]([^\'"`)]+)[\'"`]', content)
        
        if urls:
            log(f"  URLs encontradas: {len(urls)}")
            
            for url in urls:
                problems = []
                
                if "/admin/api/training/" in url:
                    problems.append("URL INCORRETA! Usar: /admin/treinamento/api/")
                    total_issues += 1
                
                if problems:
                    log(f"    PROBLEMA: {url}")
                    for p in problems:
                        log(f"      -> {p}")
                else:
                    log(f"    OK: {url}")
            log("")
        else:
            log("  Nenhuma URL encontrada")
            log("")
            
    except Exception as e:
        log(f"  ERRO: {e}")
        log("")

log("=" * 70)
log("RESUMO")
log("=" * 70)
log(f"Arquivos escaneados: {total_files}")
log(f"Problemas encontrados: {total_issues}")
log("")

if total_issues > 0:
    log("ACAO NECESSARIA!")
    log("Corrija as URLs que usam /admin/api/training/")
    log("O correto e: /admin/treinamento/api/")
else:
    log("Nenhum problema encontrado!")

log("=" * 70)

output.close()
print("\n>>> Resultado salvo em: resultado_scan.txt <<<\n")
