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

BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

TOPOLOGY_FILE = "MPLS-IOU.yml"
INVENTORY_FILE = "inventory_update_script"
PRE_DEPLOYMENT_FILE = "config_pre_deployment.json"
POST_DEPLOYMENT_FILE = "config_post_deployment.json"
COMPARATIVE_REPORT_FILE = "comparative_report.txt"
SEARCH_REPORT_FILE = "reporte_busqueda.txt"

# ============================================================
# OPCIÓN A: GENERAR INVENTARIO AUTOMÁTICAMENTE
# ============================================================

def generate_inventory():
    """
    Lee la topología YAML y genera inventario Ansible
    """
    print("\n" + "=" * 80)
    print("GENERAR INVENTARIO AUTOMÁTICAMENTE")
    print("=" * 80 + "\n")
    
    try:
        with open(TOPOLOGY_FILE, "r") as file:
            topology = yaml.safe_load(file)
        
        lab_name = topology["name"]
        nodes = topology["topology"]["nodes"]
        
        # Filtrar únicamente dispositivos Cisco IOL
        devices = []
        
        for node_name, node_data in nodes.items():
            if node_data.get("kind") == "cisco_iol":
                devices.append(f"clab-{lab_name}-{node_name}")
        
        # Ordenar alfabéticamente
        devices.sort()
        
        # Generar inventario
        with open(INVENTORY_FILE, "w") as inv:
            inv.write("[network_devices]\n")
            
            for device in devices:
                inv.write(f"{device}\n")
            
            inv.write("\n[network_devices:vars]\n")
            inv.write("ansible_user=admin\n")
            inv.write("ansible_password=admin\n")
            inv.write("ansible_network_os=cisco.ios.ios\n")
            inv.write("ansible_connection=ansible.netcommon.network_cli\n")
            inv.write("ansible_paramiko_look_for_keys=False\n")
        
        print(f"✓ Inventario generado correctamente: {INVENTORY_FILE}")
        print(f"✓ Dispositivos encontrados: {len(devices)}\n")
        
        return devices
        
    except Exception as e:
        print(f"✗ Error: {e}\n")
        return []

# ============================================================
# OPCIÓN B: COMPARAR CONFIGURACIONES PRE vs POST DESPLIEGUE
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

def capture_configurations(devices, username, password, output_file, phase):
    """
    Conecta a cada dispositivo y captura la running-config
    Guarda en archivo JSON
    """
    configs = {}
    
    for device in devices:
        hostname = device["hostname"]
        print(f"[{phase}] Conectando a {hostname}...")
        
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
            
            print(f"[{phase}] ✓ {hostname} - Configuración capturada")
            
        except Exception as e:
            configs[hostname] = {
                "timestamp": datetime.now().isoformat(),
                "running_config": None,
                "status": f"ERROR: {str(e)}"
            }
            print(f"[{phase}] ✗ {hostname} - Error: {str(e)}")
    
    # Guardar en JSON
    with open(output_file, "w") as f:
        json.dump(configs, f, indent=2)
    
    print(f"[{phase}] Configuraciones guardadas en: {output_file}\n")
    return configs

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
                for line in result["added_lines"][:50]:
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
                for line in result["removed_lines"][:50]:
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

def run_option_b(devices, username, password):
    """Ejecuta la OPCIÓN B completa"""
    
    print("\n" + "=" * 80)
    print("COMPARAR CONFIGURACIONES PRE vs POST DESPLIEGUE")
    print("=" * 80 + "\n")
    
    # Capturar PRE-DESPLIEGUE
    print("FASE 1: CAPTURA PRE-DESPLIEGUE")
    print("-" * 80)
    pre_configs = capture_configurations(devices, username, password, PRE_DEPLOYMENT_FILE, "PRE")
    
    # Instrucciones para ejecutar playbooks
    print("INFORMACIÓN:")
    print("Ahora ejecute los playbooks de Ansible de sus compañeros:")
    print("  - interfaces.yml")
    print("  - ospf.yml")
    print("  - mpls.yml")
    print("  - bgp.yml")
    print("  - vpn.yml")
    print()
    print("Puede usar el inventario generado en OPCIÓN A:")
    print(f"  ansible-playbook -i {INVENTORY_FILE} playbooks/interfaces.yml")
    print()
    input("Presione ENTER una vez que haya ejecutado todos los playbooks...")
    print()
    
    # Capturar POST-DESPLIEGUE
    print("FASE 2: CAPTURA POST-DESPLIEGUE")
    print("-" * 80)
    post_configs = capture_configurations(devices, username, password, POST_DEPLOYMENT_FILE, "POST")
    
    # Comparar
    print("Analizando diferencias...")
    comparison_results = compare_configurations(pre_configs, post_configs, devices)
    print("✓ Análisis completado\n")
    
    # Generar reporte
    print("Generando reporte...")
    generate_report(comparison_results, COMPARATIVE_REPORT_FILE)
    print(f"✓ Reporte guardado en: {COMPARATIVE_REPORT_FILE}\n")

# ============================================================
# OPCIÓN C: BUSCAR COMANDOS ESPECÍFICOS
# ============================================================

# Comandos a buscar
ROUTER_COMMANDS = [
    "router ospf",
    "router bgp",
    "mpls ip",
    "ip cef"
]

SWITCH_COMMANDS = [
    "spanning-tree mode",
    "vlan",
    "switchport mode",
    "switchport access vlan",
    "switchport mode trunk"
]

def get_devices_with_type():
    """Lee la topología y retorna dispositivos con su tipo"""
    with open(TOPOLOGY_FILE, "r") as file:
        topology = yaml.safe_load(file)
    
    lab_name = topology["name"]
    nodes = topology["topology"]["nodes"]
    
    devices = []
    
    for node_name, node_data in nodes.items():
        # Ignorar PCs Linux
        if node_data.get("kind") != "cisco_iol":
            continue
        
        if node_data.get("type") == "l2":
            tipo = "switch"
        else:
            tipo = "router"
        
        devices.append({
            "hostname": f"clab-{lab_name}-{node_name}",
            "device_type": "cisco_ios",
            "tipo": tipo
        })
    
    devices.sort(key=lambda d: d["hostname"])
    return devices

def run_option_c(username, password):
    """Ejecuta la OPCIÓN C: Búsqueda de comandos específicos"""
    
    print("\n" + "=" * 80)
    print("BUSCAR COMANDOS ESPECÍFICOS")
    print("=" * 80 + "\n")
    
    try:
        devices = get_devices_with_type()
    except Exception as e:
        print(f"✗ Error al leer topología: {e}\n")
        return
    
    with open(SEARCH_REPORT_FILE, "w") as report:
        
        report.write("=" * 70 + "\n")
        report.write("REPORTE DE BÚSQUEDA DE COMANDOS\n")
        report.write("=" * 70 + "\n\n")
        
        for device_info in devices:
            
            hostname = device_info["hostname"]
            tipo = device_info["tipo"]
            
            print(f"Conectando a {hostname}...")
            
            netmiko_device = {
                "device_type": "cisco_ios",
                "host": hostname,
                "username": username,
                "password": password,
            }
            
            try:
                
                connection = ConnectHandler(**netmiko_device)
                
                running_config = connection.send_command(
                    "show running-config"
                )
                
                connection.disconnect()
                
            except Exception as e:
                
                report.write("=" * 70 + "\n")
                report.write(f"Equipo : {hostname}\n")
                report.write(f"ERROR DE CONEXIÓN: {e}\n\n")
                
                print(f"✗ {hostname} - Error: {e}")
                continue
            
            # Seleccionar comandos según el tipo de dispositivo
            if tipo == "router":
                commands = ROUTER_COMMANDS
            else:
                commands = SWITCH_COMMANDS
            
            report.write("=" * 70 + "\n")
            report.write(f"Equipo : {hostname}\n")
            report.write(f"Tipo   : {tipo}\n\n")
            
            encontrados = 0
            
            for command in commands:
                
                if command in running_config:
                    report.write(f"[OK]            {command}\n")
                    encontrados += 1
                else:
                    report.write(f"[NO ENCONTRADO] {command}\n")
            
            report.write(
                f"\nResumen: {encontrados}/{len(commands)} comandos encontrados.\n\n"
            )
            
            print(f"✓ {hostname} - Búsqueda completada")
    
    print(f"✓ Reporte guardado en: {SEARCH_REPORT_FILE}\n")

# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================

def main():
    """Orquesta el flujo completo"""
    
    # OPCIÓN A: Generar inventario
    devices_names = generate_inventory()
    
    if not devices_names:
        print("[ERROR] No se pudieron obtener dispositivos. Abortando.")
        return
    
    # OPCIÓN B + C: Credenciales (una sola vez)
    print("[CREDENCIALES] Ingrese credenciales SSH (para OPCIÓN B y C):")
    username = input("  Usuario SSH: ")
    password = getpass("  Contraseña SSH: ")
    print()
    
    # OPCIÓN B: Comparar configuraciones
    devices = get_devices_from_topology()
    
    if not devices:
        print("[ERROR] No se pudieron obtener dispositivos. Abortando.")
        return
    
    run_option_b(devices, username, password)
    
    # OPCIÓN C: Buscar comandos específicos
    run_option_c(username, password)
    
    # Resumen final
    print("\n" + "=" * 80)
    print("PROCESO COMPLETADO - OPCIÓN A + OPCIÓN B + OPCIÓN C")
    print("=" * 80)
    print(f"\nArchivos generados:")
    print(f"  1. {INVENTORY_FILE} - Inventario Ansible")
    print(f"  2. {PRE_DEPLOYMENT_FILE} - Configuraciones pre-despliegue")
    print(f"  3. {POST_DEPLOYMENT_FILE} - Configuraciones post-despliegue")
    print(f"  4. {COMPARATIVE_REPORT_FILE} - Reporte de comparación PRE vs POST")
    print(f"  5. {SEARCH_REPORT_FILE} - Reporte de búsqueda de comandos\n")

# ============================================================
# PUNTO DE ENTRADA
# ============================================================

if __name__ == "__main__":
    main()