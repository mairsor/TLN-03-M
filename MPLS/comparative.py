import yaml
import json
from netmiko import ConnectHandler
from getpass import getpass
from pathlib import Path
import sys
from datetime import datetime

# ============================================================
# CONFIGURACIÓN
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

TOPOLOGY_FILE = "MPLS-IOU.yml"
PRE_DEPLOYMENT_FILE = "config_pre_deployment.json"
POST_DEPLOYMENT_FILE = "config_post_deployment.json"
COMPARATIVE_REPORT_FILE = "comparative_report.txt"

# ============================================================
# FUNCIÓN: Obtener lista de dispositivos desde topología
# ============================================================

def get_devices_from_topology():
    """Lee la topología y retorna lista de dispositivos Cisco IOL"""
    with open(TOPOLOGY_FILE, "r") as file:
        topology = yaml.safe_load(file)
    
    lab_name = topology["name"]
    nodes = topology["topology"]["nodes"]
    
    devices = []
    for node_name, node_data in nodes.items():
        if node_data.get("kind") == "cisco_iol":
            devices.append({
                "hostname": f"clab-{lab_name}-{node_name}",
                "device_type": "cisco_ios"
            })
    
    devices.sort(key=lambda d: d["hostname"])
    return devices

# ============================================================
# FUNCIÓN: Capturar configuraciones
# ============================================================

def capture_configurations(devices, username, password, output_file):
    """
    Conecta a cada dispositivo y captura la running-config
    Guarda en archivo JSON
    """
    configs = {}
    
    for device in devices:
        hostname = device["hostname"]
        print(f"[CAPTURA] Conectando a {hostname}...")
        
        try:
            connection = ConnectHandler(
                device_type=device["device_type"],
                host=hostname,
                username=username,
                password=password,
                timeout=10
            )
            
            running_config = connection.send_command("show running-config")
            connection.disconnect()
            
            configs[hostname] = {
                "timestamp": datetime.now().isoformat(),
                "running_config": running_config,
                "status": "OK"
            }
            
            print(f"[CAPTURA] ✓ {hostname} - Configuración capturada")
            
        except Exception as e:
            configs[hostname] = {
                "timestamp": datetime.now().isoformat(),
                "running_config": None,
                "status": f"ERROR: {str(e)}"
            }
            print(f"[CAPTURA] ✗ {hostname} - Error: {str(e)}")
    
    # Guardar en JSON
    with open(output_file, "w") as f:
        json.dump(configs, f, indent=2)
    
    print(f"\n[CAPTURA] Configuraciones guardadas en: {output_file}\n")
    return configs

# ============================================================
# FUNCIÓN: Comparar configuraciones PRE vs POST
# ============================================================

def compare_configurations(pre_configs, post_configs, devices):
    """
    Compara configuraciones PRE vs POST
    Retorna diccionario con análisis de diferencias
    """
    comparison_results = {}
    
    for device in devices:
        hostname = device["hostname"]
        
        pre_config = pre_configs.get(hostname, {}).get("running_config", "")
        post_config = post_configs.get(hostname, {}).get("running_config", "")
        pre_status = pre_configs.get(hostname, {}).get("status", "UNKNOWN")
        post_status = post_configs.get(hostname, {}).get("status", "UNKNOWN")
        
        # Si hay errores, registrar
        if pre_status != "OK" or post_status != "OK":
            comparison_results[hostname] = {
                "status": "ERROR",
                "pre_status": pre_status,
                "post_status": post_status,
                "added_lines": [],
                "removed_lines": [],
                "changes_count": 0
            }
            continue
        
        # Comparar líneas
        pre_lines = set(pre_config.split("\n"))
        post_lines = set(post_config.split("\n"))
        
        added_lines = sorted(post_lines - pre_lines)
        removed_lines = sorted(pre_lines - post_lines)
        
        # Filtrar líneas vacías y comentarios iniciales
        added_lines = [l.strip() for l in added_lines if l.strip() and not l.startswith("!")]
        removed_lines = [l.strip() for l in removed_lines if l.strip() and not l.startswith("!")]
        
        total_changes = len(added_lines) + len(removed_lines)
        
        comparison_results[hostname] = {
            "status": "OK",
            "pre_status": pre_status,
            "post_status": post_status,
            "added_lines": added_lines,
            "removed_lines": removed_lines,
            "changes_count": total_changes,
            "pre_lines_count": len(pre_lines),
            "post_lines_count": len(post_lines)
        }
    
    return comparison_results

# ============================================================
# FUNCIÓN: Generar reporte
# ============================================================

def generate_report(comparison_results, report_file):
    """Genera reporte en formato TXT con análisis de cambios"""
    
    with open(report_file, "w") as report:
        # Encabezado
        report.write("=" * 80 + "\n")
        report.write("REPORTE DE COMPARACIÓN PRE vs POST DESPLIEGUE ANSIBLE\n")
        report.write("=" * 80 + "\n")
        report.write(f"Fecha y Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        report.write("=" * 80 + "\n\n")
        
        # Estadísticas generales
        total_devices = len(comparison_results)
        devices_ok = sum(1 for r in comparison_results.values() if r["status"] == "OK")
        devices_error = total_devices - devices_ok
        total_changes = sum(r.get("changes_count", 0) for r in comparison_results.values())
        
        report.write("ESTADÍSTICAS GENERALES\n")
        report.write("-" * 80 + "\n")
        report.write(f"Total de dispositivos: {total_devices}\n")
        report.write(f"Dispositivos procesados correctamente: {devices_ok}\n")
        report.write(f"Dispositivos con error: {devices_error}\n")
        report.write(f"Total de cambios detectados: {total_changes}\n\n")
        
        # Análisis por dispositivo
        report.write("=" * 80 + "\n")
        report.write("ANÁLISIS POR DISPOSITIVO\n")
        report.write("=" * 80 + "\n\n")
        
        for hostname, result in sorted(comparison_results.items()):
            report.write("=" * 80 + "\n")
            report.write(f"Dispositivo: {hostname}\n")
            report.write(f"Estado Pre-Despliegue: {result['pre_status']}\n")
            report.write(f"Estado Post-Despliegue: {result['post_status']}\n")
            
            if result["status"] == "ERROR":
                report.write(f"ESTADO GENERAL: ERROR\n")
                report.write(f"No fue posible capturar configuración de este dispositivo.\n\n")
                continue
            
            report.write(f"Líneas Pre-Despliegue: {result['pre_lines_count']}\n")
            report.write(f"Líneas Post-Despliegue: {result['post_lines_count']}\n")
            report.write(f"Total de cambios: {result['changes_count']}\n\n")
            
            # Líneas agregadas
            if result["added_lines"]:
                report.write("LÍNEAS AGREGADAS POR ANSIBLE:\n")
                report.write("-" * 80 + "\n")
                for line in result["added_lines"][:50]:  # Máximo 50 líneas
                    report.write(f" + {line}\n")
                if len(result["added_lines"]) > 50:
                    report.write(f" ... y {len(result['added_lines']) - 50} líneas más\n")
                report.write("\n")
            else:
                report.write("LÍNEAS AGREGADAS: Ninguna\n\n")
            
            # Líneas removidas
            if result["removed_lines"]:
                report.write("LÍNEAS REMOVIDAS POR ANSIBLE:\n")
                report.write("-" * 80 + "\n")
                for line in result["removed_lines"][:50]:  # Máximo 50 líneas
                    report.write(f" - {line}\n")
                if len(result["removed_lines"]) > 50:
                    report.write(f" ... y {len(result['removed_lines']) - 50} líneas más\n")
                report.write("\n")
            else:
                report.write("LÍNEAS REMOVIDAS: Ninguna\n\n")
        
        # Resumen final
        report.write("=" * 80 + "\n")
        report.write("RESUMEN FINAL\n")
        report.write("=" * 80 + "\n")
        report.write(f"Reporte generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        report.write(f"Archivos de referencia:\n")
        report.write(f"  - PRE-Despliegue: {PRE_DEPLOYMENT_FILE}\n")
        report.write(f"  - POST-Despliegue: {POST_DEPLOYMENT_FILE}\n")
        report.write("=" * 80 + "\n")

# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================

def main():
    """Orquesta el flujo completo"""
    
    print("\n" + "=" * 80)
    print("SCRIPT DE COMPARACIÓN PRE vs POST DESPLIEGUE ANSIBLE")
    print("=" * 80 + "\n")
    
    # Paso 1: Obtener dispositivos de topología
    print("[INICIO] Leyendo topología...")
    try:
        devices = get_devices_from_topology()
        print(f"[INICIO] ✓ {len(devices)} dispositivos encontrados\n")
    except Exception as e:
        print(f"[ERROR] No se pudo leer la topología: {e}")
        return
    
    # Paso 2: Credenciales
    print("[CREDENCIALES] Ingrese credenciales SSH:")
    username = input("  Usuario SSH: ")
    password = getpass("  Contraseña SSH: ")
    print()
    
    # Paso 3: Capturar PRE-DESPLIEGUE
    print("[FASE 1] CAPTURA PRE-DESPLIEGUE")
    print("-" * 80)
    pre_configs = capture_configurations(devices, username, password, PRE_DEPLOYMENT_FILE)
    
    # Paso 4: Instrucciones para ejecutar playbooks
    print("[INFORMACIÓN] ")
    print("Ahora ejecute los playbooks de Ansible:")
    print("  - interfaces.yml")
    print("  - ospf.yml")
    print("  - mpls.yml")
    print("  - bgp.yml")
    print("  - vpn.yml")
    print()
    input("Presione ENTER una vez que haya ejecutado todos los playbooks...")
    print()
    
    # Paso 5: Capturar POST-DESPLIEGUE
    print("[FASE 2] CAPTURA POST-DESPLIEGUE")
    print("-" * 80)
    post_configs = capture_configurations(devices, username, password, POST_DEPLOYMENT_FILE)
    
    # Paso 6: Comparar
    print("[COMPARACIÓN] Analizando diferencias...")
    comparison_results = compare_configurations(pre_configs, post_configs, devices)
    print("[COMPARACIÓN] ✓ Análisis completado\n")
    
    # Paso 7: Generar reporte
    print("[REPORTE] Generando reporte...")
    generate_report(comparison_results, COMPARATIVE_REPORT_FILE)
    print(f"[REPORTE] ✓ Reporte guardado en: {COMPARATIVE_REPORT_FILE}\n")
    
    print("=" * 80)
    print("PROCESO COMPLETADO")
    print("=" * 80)
    print(f"\nArchivos generados:")
    print(f"  1. {PRE_DEPLOYMENT_FILE} - Configuraciones pre-despliegue")
    print(f"  2. {POST_DEPLOYMENT_FILE} - Configuraciones post-despliegue")
    print(f"  3. {COMPARATIVE_REPORT_FILE} - Reporte de comparación\n")

# ============================================================
# PUNTO DE ENTRADA
# ============================================================

if __name__ == "__main__":
    main()