# pipeline_runner.py (Versão Nativa Databricks)
from datetime import datetime

def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")

def main():
    log("=" * 60)
    log("PIPELINE OLIST — MEDALLION ARCHITECTURE (DATABRICKS NATIVE)")
    log("=" * 60)
   
    steps = [
        ("Bronze", "/Workspace/Projeto_Framework-Rethink/notebooks/01 - Bronze"),
        ("Silver", "/Workspace/Projeto_Framework-Rethink/notebooks/02 - Silver"),
        ("Gold",   "/Workspace/Projeto_Framework-Rethink/notebooks/03 - Gold"), 
    ]

    for name, notebook_path in steps:
        log(f"▶  Iniciando etapa: {name} (Notebook: {notebook_path})")
        
        try:
            dbutils.notebook.run(notebook_path, 600)
            
            log(f"✅ Etapa concluída: {name}")
            log("-" * 60)
            
        except Exception as e:
            log(f"❌ Falha na etapa {name}.")
            log(f"Detalhes do erro do Databricks: {str(e)}")
            log("⚠️ Abortando as próximas etapas devido à falha.")
            
            raise Exception(f"Pipeline abortado na camada: {name}") 

    log("🎉 Pipeline finalizado com sucesso!")

if __name__ == "__main__":
    main()