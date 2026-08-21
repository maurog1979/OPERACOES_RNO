#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AUTOMAÇÃO DO FLUXO DE TRABALHO - PAINEL SAFRA
=============================================
Detecta automaticamente se está no trabalho ou em casa
e executa as ações apropriadas.

NO TRABALHO (fim do expediente):
- Verifica alterações pendentes
- Faz backup do banco
- Sincroniza OneDrive
- Gera relatório do dia

EM CASA (início do desenvolvimento):
- Verifica se OneDrive sincronizou
- Restaura o banco
- Testa a conexão
- Abre o navegador no dashboard

Uso:
    python sincronizar_projeto.py

Ou com parâmetros:
    python sincronizar_projeto.py --backup   (força backup)
    python sincronizar_projeto.py --restore  (força restore)
    python sincronizar_projeto.py --status   (mostra status atual)
"""

import os
import sys
import subprocess
import platform
import shutil
import json
from datetime import datetime
from pathlib import Path
import hashlib
import time

# ============================================================
# CONFIGURAÇÕES
# ============================================================

PROJECT_NAME = "OPERACOES_RNO"
USERNAME = os.getlogin()
HOSTNAME = platform.node()
IS_WORK = "CLARO" in HOSTNAME.upper() or "N5996917" in USERNAME.upper()
IS_HOME = "DGS" in USERNAME.upper() or not IS_WORK

# Caminhos baseados no usuário
if IS_WORK:
    BASE_PATH = f"C:\\Users\\{USERNAME}\\OneDrive - Claro SA\\INTRANET\\{PROJECT_NAME}"
else:
    BASE_PATH = f"C:\\Users\\{USERNAME}\\OneDrive - Claro SA\\INTRANET\\{PROJECT_NAME}"

# Subdiretórios
BACKUP_DIR = os.path.join(BASE_PATH, "database", "dumps")
BACKUP_FILE = os.path.join(BACKUP_DIR, "ultimo_backup.sql")
BACKUP_HISTORY = os.path.join(BACKUP_DIR, "history.json")

# Comandos
MYSQLDUMP = r"C:\laragon\bin\mysql\mysql-8.4.3-winx64\bin\mysqldump.exe"
MYSQL = r"C:\laragon\bin\mysql\mysql-8.4.3-winx64\bin\mysql.exe"

# Arquivos do projeto
PROJECT_FILES = [
    "areas/adm/desconexao/dash_safra.py",
    "areas/adm/desconexao/templates/dash_safra.html",
    "app.py",
    "sincronizar_projeto.py"
]

# ============================================================
# FUNÇÕES DE UTILIDADE
# ============================================================

def log(msg, level="INFO"):
    """Log com timestamp."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {level}: {msg}")
    return f"[{timestamp}] {level}: {msg}"

def get_file_hash(filepath):
    """Calcula MD5 de um arquivo."""
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

def get_file_info(filepath):
    """Retorna informações do arquivo."""
    if not os.path.exists(filepath):
        return None
    stat = os.stat(filepath)
    return {
        'size': stat.st_size,
        'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
        'hash': get_file_hash(filepath)
    }

def run_command(cmd, capture=False):
    """Executa comando e retorna resultado."""
    try:
        if capture:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            return result.stdout.strip(), result.returncode == 0
        else:
            result = subprocess.run(cmd, shell=True)
            return result.stdout, result.returncode == 0
    except Exception as e:
        return str(e), False

# ============================================================
# FUNÇÕES DE DIAGNÓSTICO
# ============================================================

def diagnostico_ambiente():
    """Diagnostica o ambiente atual."""
    lines = []
    lines.append(log("=" * 70))
    lines.append(log(" DIAGNÓSTICO DE AMBIENTE"))
    lines.append(log("=" * 70))
    lines.append(log(f"Computador: {HOSTNAME}"))
    lines.append(log(f"Usuário: {USERNAME}"))
    lines.append(log(f"Ambiente: {'TRABALHO' if IS_WORK else 'CASA'}"))
    lines.append(log(f"Projeto: {BASE_PATH}"))
    lines.append(log("-" * 70))
    
    # Verifica arquivos do projeto
    lines.append(log("\n📁 Arquivos do Projeto:"))
    for rel_path in PROJECT_FILES:
        full_path = os.path.join(BASE_PATH, rel_path)
        if os.path.exists(full_path):
            info = get_file_info(full_path)
            lines.append(log(f"  ✅ {rel_path} ({info['size']:,} bytes)"))
        else:
            lines.append(log(f"  ❌ {rel_path} (NÃO ENCONTRADO)"))
    
    # Verifica backup
    lines.append(log("\n💾 Último Backup:"))
    if os.path.exists(BACKUP_FILE):
        info = get_file_info(BACKUP_FILE)
        lines.append(log(f"  ✅ {BACKUP_FILE} ({info['size']:,} bytes)"))
        lines.append(log(f"     Modificado: {info['modified']}"))
    else:
        lines.append(log(f"  ❌ Nenhum backup encontrado"))
    
    return lines

def diagnostico_banco():
    """Diagnostica o banco de dados."""
    lines = []
    lines.append(log("\n" + "-" * 70))
    lines.append(log(" BANCO DE DADOS"))
    lines.append(log("-" * 70))
    
    # Testa conexão
    try:
        import pymysql
        conn = pymysql.connect(
            host='localhost',
            user='root',
            password='',
            database='safra',
            port=3306
        )
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            tables = [row[0] for row in cur.fetchall()]
            lines.append(log(f"✅ Conectado ao banco 'safra'"))
            lines.append(log(f"   Tabelas: {', '.join(tables) if tables else 'NENHUMA'}"))
            
            # Verifica registros
            for table in ['safra_metas', 'safra_resumo_mensal', 'safra_resumo_diario']:
                if table in tables:
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cur.fetchone()[0]
                    lines.append(log(f"   {table}: {count:,} registros"))
        conn.close()
    except Exception as e:
        lines.append(log(f"❌ Erro ao conectar: {e}"))
    
    return lines

# ============================================================
# FUNÇÕES DE BACKUP
# ============================================================

def fazer_backup():
    """Faz backup do banco de dados."""
    log("=" * 70, "BACKUP")
    log("=" * 70, "BACKUP")
    
    # Cria diretório de backup
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    # Nome do backup com timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"safra_backup_{timestamp}.sql")
    
    # Executa dump
    cmd = f'"{MYSQLDUMP}" -u root safra > "{backup_file}"'
    log(f"Executando: {cmd}")
    
    output, success = run_command(cmd)
    
    if success and os.path.exists(backup_file) and os.path.getsize(backup_file) > 0:
        size = os.path.getsize(backup_file)
        log(f"✅ Backup criado: {backup_file} ({size:,} bytes)")
        
        # Atualiza último backup
        shutil.copy2(backup_file, BACKUP_FILE)
        log(f"✅ Último backup atualizado: {BACKUP_FILE}")
        
        # Salva histórico
        history = []
        if os.path.exists(BACKUP_HISTORY):
            with open(BACKUP_HISTORY, 'r') as f:
                history = json.load(f)
        
        history.append({
            'file': os.path.basename(backup_file),
            'timestamp': timestamp,
            'size': size,
            'host': HOSTNAME
        })
        
        with open(BACKUP_HISTORY, 'w') as f:
            json.dump(history, f, indent=2)
        
        return True
    else:
        log(f"❌ Falha no backup: {output}")
        return False

def restaurar_backup():
    """Restaura o banco de dados do último backup."""
    log("=" * 70, "RESTORE")
    log("=" * 70, "RESTORE")
    
    if not os.path.exists(BACKUP_FILE):
        log(f"❌ Backup não encontrado: {BACKUP_FILE}")
        return False
    
    # Verifica se o backup é válido
    if os.path.getsize(BACKUP_FILE) == 0:
        log(f"❌ Backup vazio: {BACKUP_FILE}")
        return False
    
    # Confirmação (se não for automático)
    if not os.environ.get('AUTO_RESTORE'):
        log("⚠️ Isso vai SUBSTITUIR o banco atual!")
        resposta = input("Deseja continuar? (s/N): ")
        if resposta.lower() != 's':
            log("Restore cancelado")
            return False
    
    # Executa restore
    cmd = f'"{MYSQL}" -u root safra < "{BACKUP_FILE}"'
    log(f"Executando: {cmd}")
    
    output, success = run_command(cmd)
    
    if success:
        log(f"✅ Banco restaurado com sucesso!")
        # Testa a restauração
        testar_conexao()
        return True
    else:
        log(f"❌ Falha no restore: {output}")
        return False

# ============================================================
# FUNÇÕES DE TESTE
# ============================================================

def testar_conexao():
    """Testa a conexão com o banco após restore."""
    log("\n" + "-" * 70)
    log(" TESTANDO CONEXÃO")
    log("-" * 70)
    
    try:
        import pymysql
        conn = pymysql.connect(
            host='localhost',
            user='root',
            password='',
            database='safra',
            port=3306
        )
        
        with conn.cursor() as cur:
            # Verifica tabelas
            cur.execute("SHOW TABLES")
            tables = [row[0] for row in cur.fetchall()]
            log("✅ Conectado ao banco 'safra'")
            
            for table in ['safra_metas', 'safra_resumo_mensal', 'safra_resumo_diario']:
                if table in tables:
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cur.fetchone()[0]
                    if count > 0:
                        log(f"  ✅ {table}: {count:,} registros")
                    else:
                        log(f"  ⚠️ {table}: {count} registros (VAZIO!)")
                else:
                    log(f"  ❌ {table}: NÃO ENCONTRADA")
        
        conn.close()
        
        # Testa API
        testar_api()
        
        return True
    except Exception as e:
        log(f"❌ Erro no teste: {e}")
        return False

def testar_api():
    """Testa as APIs do dashboard."""
    log("\n" + "-" * 70)
    log(" TESTANDO APIs")
    log("-" * 70)
    
    try:
        import requests
        
        endpoints = [
            '/dash/safra/api/diagnostico',
            '/dash/safra/api/options',
            '/dash/safra/api/data'
        ]
        
        for endpoint in endpoints:
            url = f"http://localhost:5000{endpoint}"
            try:
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('ok'):
                        log(f"  ✅ {endpoint}: OK")
                    else:
                        log(f"  ⚠️ {endpoint}: {data.get('erro', 'Erro desconhecido')}")
                else:
                    log(f"  ❌ {endpoint}: Status {response.status_code}")
            except requests.exceptions.ConnectionError:
                log(f"  ❌ {endpoint}: Flask não está rodando")
            except Exception as e:
                log(f"  ❌ {endpoint}: {e}")
                
    except ImportError:
        log("  ⚠️ requests não instalado, pulando teste de API")

# ============================================================
# FLUXO DE TRABALHO AUTOMATIZADO
# ============================================================

def fluxo_trabalho():
    """Executa o fluxo de trabalho completo."""
    log("\n" + "=" * 70)
    log(" FLUXO DE TRABALHO AUTOMATIZADO")
    log("=" * 70)
    log(f"Ambiente: {'TRABALHO' if IS_WORK else 'CASA'}")
    log(f"Horário: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 70)
    
    if IS_WORK:
        log("\n🏢 FLUXO - TRABALHO (Fim do expediente)")
        log("-" * 70)
        
        # 1. Diagnóstico rápido
        log("\n1. Diagnóstico do ambiente...")
        diagnostico_ambiente()
        
        # 2. Verifica alterações
        log("\n2. Verificando arquivos modificados...")
        for rel_path in PROJECT_FILES:
            full_path = os.path.join(BASE_PATH, rel_path)
            if os.path.exists(full_path):
                info = get_file_info(full_path)
                log(f"  📄 {rel_path}: {info['size']:,} bytes")
        
        # 3. Faz backup
        log("\n3. Fazendo backup do banco...")
        if fazer_backup():
            log("✅ Backup concluído com sucesso!")
        else:
            log("❌ Falha no backup!")
        
        # 4. Sincroniza OneDrive (força)
        log("\n4. Sincronizando OneDrive...")
        # O OneDrive sincroniza automaticamente, mas podemos forçar
        # Envia notificação (opcional)
        
        # 5. Gera relatório do dia
        log("\n5. Gerando relatório do dia...")
        relatorio = {
            'data': datetime.now().isoformat(),
            'host': HOSTNAME,
            'arquivos': {
                f: get_file_info(os.path.join(BASE_PATH, f)) 
                for f in PROJECT_FILES
            },
            'backup': {
                'arquivo': os.path.basename(BACKUP_FILE),
                'tamanho': os.path.getsize(BACKUP_FILE) if os.path.exists(BACKUP_FILE) else 0
            }
        }
        
        relatorio_path = os.path.join(BASE_PATH, f"relatorio_{datetime.now().strftime('%Y%m%d')}.json")
        with open(relatorio_path, 'w') as f:
            json.dump(relatorio, f, indent=2)
        
        log(f"✅ Relatório salvo: {relatorio_path}")
        
        # 6. Mensagem final
        log("\n" + "=" * 70)
        log("✅ FLUXO CONCLUÍDO - TRABALHO")
        log("=" * 70)
        log("Agora você pode ir para casa!")
        log("O OneDrive vai sincronizar automaticamente.")
        log("Em casa, execute este mesmo script para restaurar.")
        
    else:  # CASA
        log("\n🏠 FLUXO - CASA (Início do desenvolvimento)")
        log("-" * 70)
        
        # 1. Verifica se OneDrive sincronizou
        log("\n1. Verificando sincronia do OneDrive...")
        
        # Verifica se o backup está disponível
        if not os.path.exists(BACKUP_FILE):
            log(f"❌ Backup não encontrado! Aguarde o OneDrive sincronizar.")
            log(f"   Arquivo esperado: {BACKUP_FILE}")
            return False
        
        # 2. Diagnóstico rápido
        log("\n2. Diagnóstico do ambiente...")
        diagnostico_ambiente()
        
        # 3. Restaura banco
        log("\n3. Restaurando banco...")
        os.environ['AUTO_RESTORE'] = '1'  # Pula confirmação
        if restaurar_backup():
            log("✅ Banco restaurado com sucesso!")
        else:
            log("❌ Falha no restore!")
            return False
        
        # 4. Testa conexão
        log("\n4. Testando conexão...")
        testar_conexao()
        
        # 5. Abre o dashboard no navegador
        log("\n5. Abrindo dashboard no navegador...")
        try:
            import webbrowser
            webbrowser.open("http://localhost:5000/dash/safra/")
            log("✅ Navegador aberto!")
        except Exception as e:
            log(f"⚠️ Não foi possível abrir o navegador: {e}")
            log("   Acesse manualmente: http://localhost:5000/dash/safra/")
        
        # 6. Mensagem final
        log("\n" + "=" * 70)
        log("✅ FLUXO CONCLUÍDO - CASA")
        log("=" * 70)
        log("Ambiente pronto para desenvolvimento!")
        log("Lembre-se de fazer backup antes de sair.")
    
    return True

# ============================================================
# FUNÇÃO PRINCIPAL
# ============================================================

def main():
    """Função principal."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Automação do fluxo de trabalho do Painel Safra')
    parser.add_argument('--backup', action='store_true', help='Força backup do banco')
    parser.add_argument('--restore', action='store_true', help='Força restore do banco')
    parser.add_argument('--status', action='store_true', help='Mostra status atual')
    parser.add_argument('--diagnostico', action='store_true', help='Executa diagnóstico completo')
    
    args = parser.parse_args()
    
    if args.status:
        log("📊 STATUS DO AMBIENTE")
        log("=" * 70)
        diagnostico_ambiente()
        diagnostico_banco()
        return
    
    if args.diagnostico:
        log("🔍 DIAGNÓSTICO COMPLETO")
        log("=" * 70)
        diagnostico_ambiente()
        diagnostico_banco()
        return
    
    if args.backup:
        log("💾 BACKUP FORÇADO")
        log("=" * 70)
        fazer_backup()
        return
    
    if args.restore:
        log("🔄 RESTORE FORÇADO")
        log("=" * 70)
        restaurar_backup()
        return
    
    # Executa fluxo automático
    fluxo_trabalho()

if __name__ == "__main__":
    main()