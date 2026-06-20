# network_automation_suite.py
"""
AUTOMATIZACIÓN Y PROGRAMABILIDAD DE REDES - TLN03
Solución integrada para gestión de topología MPLS L3VPN

Autor: Antonio
Descripción: Script que automatiza tareas de operación de red
  - Opción A: Generar inventarios automáticamente
  - Opción B: Comparar configuraciones PRE vs POST
  - Opción C: Buscar comandos específicos
  - Opción D: Generar reportes en formato TXT (INTEGRADO)

Uso:
    python network_automation_suite.py
"""

import yaml
import json
from netmiko import ConnectHandler
from getpass import getpass
from pathlib import Path
import sys
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import logging

# ============================================================
# CONFIGURACIÓN Y LOGGING
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

# Archivos de configuración
TOPOLOGY_FILE = "MPLS-IOU.yml"
INVENTORY_FILE = "inventory.txt"
INVENTORY_DETAILED_FILE = "inventory_detailed.txt"
PRE_DEPLOYMENT_FILE = "config_pre_deployment.json"
POST_DEPLOYMENT_FILE = "config_post_deployment.json"
MASTER_REPORT_FILE = "master_report.txt"
SEARCH_REPORT_FILE = "reporte_busqueda.txt"

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Comandos a buscar por tipo de dispositivo
ROUTER_COMMANDS = [
    "router ospf",
    "router bgp",
    "mpls ip",
    "ip cef",
    "mpls ldp",
    "vrf"
]

SWITCH_COMMANDS = [
    "spanning-tree mode",
    "vlan",
    "switchport mode",
    "switchport access vlan",
    "switchport mode trunk"
]

# ============================================================
# CLASE: GESTOR DE TOPOLOGÍA
# ============================================================

class TopologyManager:
    """Gestiona la lectura y procesamiento de topología YAML"""
    
    def __init__(self, topology_file: str):
        self.topology_file = topology_file
        self.topology = None
        self.devices = []
        self.lab_name = None
        
    def load_topology(self) -> bool:
        """Carga la topología desde archivo YAML"""
        try:
            with open(self.topology_file, "r") as file:
                self.topology = yaml.safe_load(file)
            self.lab_name = self.topology["name"]
            logger.info(f"✓ Topología cargada: {self.lab_name}")
            return True
        except Exception as e:
            logger.error(f"✗ Error al cargar topología: {e}")
            return False
    
    def get_devices(self, device_type: str = "all") -> List[Dict]:
        """
        Retorna lista de dispositivos desde la topología
        
        Args:
            device_type: "all", "cisco_iol", "linux"
        
        Returns:
            Lista de diccionarios con información de dispositivos
        """
        if not self.topology:
            logger.error("Topología no cargada")
            return []
        
        nodes = self.topology["topology"]["nodes"]
        devices = []
        
        for node_name, node_data in nodes.items():
            if device_type == "all" or node_data.get("kind") == device_type:
                device_info = {
                    "name": node_name,
                    "hostname": f"clab-{self.lab_name}-{node_name}",
                    "kind": node_data.get("kind"),
                    "image": node_data.get("image", "N/A"),
                    "type": node_data.get("type", "router")
                }
                devices.append(device_info)
        
        # Ordenar alfabéticamente
        devices.sort(key=lambda d: d["hostname"])
        return devices
    
    def get_cisco_devices(self) -> List[Dict]:
        """Retorna solo dispositivos Cisco IOS"""
        devices = self.get_devices("cisco_iol")
        for dev in devices:
            if dev["type"] == "l2":
                dev["device_type"] = "switch"
            else:
                dev["device_type"] = "router"
        return devices


# ============================================================
# CLASE: CONECTOR DE DISPOSITIVOS
# ============================================================

class DeviceConnector:
    """Gestiona conexiones SSH a dispositivos de red"""
    
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.timeout = 10
    
    def connect(self, hostname: str, device_type: str = "cisco_ios") -> Optional[ConnectHandler]:
        """
        Establece conexión con un dispositivo
        
        Args:
            hostname: IP o nombre del dispositivo
            device_type: Tipo de dispositivo (cisco_ios por defecto)
        
        Returns:
            Objeto ConnectHandler o None si falla
        """
        try:
            connection = ConnectHandler(
                device_type=device_type,
                host=hostname,
                username=self.username,
                password=self.password,
                timeout=self.timeout
            )
            logger.info(f"✓ Conectado a {hostname}")
            return connection
        except Exception as e:
            logger.error(f"✗ Error conectando a {hostname}: {str(e)}")
            return None
    
    def get_running_config(self, connection: ConnectHandler) -> Optional[str]:
        """Obtiene running-config del dispositivo"""
        try:
            config = connection.send_command("show running-config")
            return config
        except Exception as e:
            logger.error(f"Error obteniendo config: {e}")
            return None
    
    def disconnect(self, connection: ConnectHandler):
        """Cierra conexión con dispositivo"""
        try:
            connection.disconnect()
        except Exception as e:
            logger.error(f"Error desconectando: {e}")


# ============================================================
# CLASE: ANALIZADOR DE CONFIGURACIONES
# ============================================================

class ConfigAnalyzer:
    """Analiza y compara configuraciones de dispositivos"""
    
    @staticmethod
    def compare_configs(pre_config: str, post_config: str) -> Dict:
        """
        Compara dos configuraciones
        
        Args:
            pre_config: Configuración previa
            post_config: Configuración posterior
        
        Returns:
            Diccionario con líneas agregadas/removidas
        """
        pre_lines = set(pre_config.split("\n"))
        post_lines = set(post_config.split("\n"))
        
        added_lines = sorted(post_lines - pre_lines)
        removed_lines = sorted(pre_lines - post_lines)
        
        # Filtrar líneas vacías y comentarios
        added_lines = [l.strip() for l in added_lines 
                      if l.strip() and not l.startswith("!")]
        removed_lines = [l.strip() for l in removed_lines 
                        if l.strip() and not l.startswith("!")]
        
        return {
            "added": added_lines,
            "removed": removed_lines,
            "total_changes": len(added_lines) + len(removed_lines),
            "pre_lines": len(pre_lines),
            "post_lines": len(post_lines)
        }
    
    @staticmethod
    def search_commands(config: str, commands: List[str]) -> Dict:
        """
        Busca comandos específicos en configuración
        
        Args:
            config: Contenido de running-config
            commands: Lista de comandos a buscar
        
        Returns:
            Diccionario con resultados de búsqueda
        """
        results = {
            "found": [],
            "not_found": [],
            "total_found": 0
        }
        
        for command in commands:
            if command in config:
                results["found"].append(command)
                results["total_found"] += 1
            else:
                results["not_found"].append(command)
        
        return results


# ============================================================
# CLASE: GENERADOR DE REPORTES
# ============================================================

class ReportGenerator:
    """Genera reportes en formato TXT"""
    
    def __init__(self, master_report_file: str, inventory_file: str):
        self.master_report = master_report_file
        self.inventory_file = inventory_file
        self.report_content = []
    
    def add_section(self, title: str, content: str, separator: str = "="):
        """Agrega una sección al reporte"""
        self.report_content.append(f"{separator * 80}")
        self.report_content.append(title)
        self.report_content.append(f"{separator * 80}")
        self.report_content.append(content)
        self.report_content.append("")
    
    def add_subsection(self, title: str, separator: str = "-"):
        """Agrega una subsección"""
        self.report_content.append(f"{separator * 80}")
        self.report_content.append(title)
        self.report_content.append(f"{separator * 80}")
        self.report_content.append("")
    
    def generate_inventory_section(self, devices: List[Dict]) -> str:
        """Genera sección de inventario"""
        content = []
        content.append(f"Total de dispositivos: {len(devices)}\n")
        
        content.append("LISTADO DE DISPOSITIVOS:")
        content.append("-" * 80)
        
        routers = [d for d in devices if d.get("device_type") == "router"]
        switches = [d for d in devices if d.get("device_type") == "switch"]
        
        content.append(f"\nROUTERS ({len(routers)}):")
        for router in routers:
            content.append(f"  • {router['hostname']:30} | Imagen: {router['image']}")
        
        content.append(f"\nSWITCHES ({len(switches)}):")
        for switch in switches:
            content.append(f"  • {switch['hostname']:30} | Imagen: {switch['image']}")
        
        return "\n".join(content)
    
    def generate_statistics_section(self, devices: List[Dict], 
                                   routers: int, switches: int) -> str:
        """Genera sección de estadísticas"""
        content = []
        content.append(f"Total de dispositivos: {len(devices)}")
        content.append(f"Routers: {routers}")
        content.append(f"Switches: {switches}")
        content.append(f"Fecha de generación: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        return "\n".join(content)
    
    def save_master_report(self):
        """Guarda el reporte maestro"""
        try:
            with open(self.master_report, "w") as f:
                f.write("\n".join(self.report_content))
            logger.info(f"✓ Reporte maestro guardado: {self.master_report}")
            return True
        except Exception as e:
            logger.error(f"✗ Error guardando reporte: {e}")
            return False
    
    def save_inventory_file(self, inventory_content: str):
        """Guarda archivo de inventario separado"""
        try:
            with open(self.inventory_file, "w") as f:
                f.write(inventory_content)
            logger.info(f"✓ Inventario guardado: {self.inventory_file}")
            return True
        except Exception as e:
            logger.error(f"✗ Error guardando inventario: {e}")
            return False


# ============================================================
# OPCIÓN A: GENERAR INVENTARIO
# ============================================================

def option_a_generate_inventory(topology_manager: TopologyManager) -> List[Dict]:
    """
    OPCIÓN A: Genera inventario automáticamente desde topología
    """
    print("\n" + "=" * 80)
    print("OPCIÓN A: GENERAR INVENTARIO AUTOMÁTICAMENTE")
    print("=" * 80 + "\n")
    
    try:
        devices = topology_manager.get_cisco_devices()
        
        print(f"✓ Inventario generado")
        print(f"✓ Dispositivos encontrados: {len(devices)}\n")
        
        for device in devices:
            print(f"  • {device['hostname']:30} ({device['device_type']})")
        
        return devices
        
    except Exception as e:
        print(f"✗ Error: {e}\n")
        return []


# ============================================================
# OPCIÓN B: COMPARAR CONFIGURACIONES
# ============================================================

def option_b_compare_configs(devices: List[Dict], connector: DeviceConnector,
                            analyzer: ConfigAnalyzer) -> Dict:
    """
    OPCIÓN B: Compara configuraciones PRE vs POST
    """
    print("\n" + "=" * 80)
    print("OPCIÓN B: COMPARAR CONFIGURACIONES PRE vs POST")
    print("=" * 80 + "\n")
    
    comparison_results = {}
    
    # Intentar cargar configuraciones pre-existentes
    pre_configs = {}
    post_configs = {}
    
    try:
        with open(PRE_DEPLOYMENT_FILE, "r") as f:
            pre_configs = json.load(f)
        print(f"✓ Configuraciones PRE cargadas desde {PRE_DEPLOYMENT_FILE}\n")
    except:
        print(f"⚠ No se encontraron configuraciones PRE. Capturando...\n")
        print("FASE 1: CAPTURA PRE-DESPLIEGUE")
        print("-" * 80)
        
        for device in devices:
            hostname = device["hostname"]
            print(f"[PRE] Conectando a {hostname}...")
            
            connection = connector.connect(hostname)
            if connection:
                config = connector.get_running_config(connection)
                connector.disconnect(connection)
                
                if config:
                    pre_configs[hostname] = {
                        "timestamp": datetime.now().isoformat(),
                        "running_config": config,
                        "status": "OK"
                    }
                    print(f"[PRE] ✓ {hostname} capturada")
                else:
                    pre_configs[hostname] = {
                        "timestamp": datetime.now().isoformat(),
                        "running_config": None,
                        "status": "ERROR: No se pudo obtener config"
                    }
                    print(f"[PRE] ✗ {hostname} error")
        
        with open(PRE_DEPLOYMENT_FILE, "w") as f:
            json.dump(pre_configs, f, indent=2)
        print(f"\n✓ Configuraciones PRE guardadas en {PRE_DEPLOYMENT_FILE}\n")
    
    # Obtener configuraciones POST
    print("FASE 2: CAPTURA POST-DESPLIEGUE")
    print("-" * 80)
    print("Ingrese las credenciales para capturar POST-despliegue:")
    
    for device in devices:
        hostname = device["hostname"]
        print(f"[POST] Conectando a {hostname}...")
        
        connection = connector.connect(hostname)
        if connection:
            config = connector.get_running_config(connection)
            connector.disconnect(connection)
            
            if config:
                post_configs[hostname] = {
                    "timestamp": datetime.now().isoformat(),
                    "running_config": config,
                    "status": "OK"
                }
                print(f"[POST] ✓ {hostname} capturada")
            else:
                post_configs[hostname] = {
                    "timestamp": datetime.now().isoformat(),
                    "running_config": None,
                    "status": "ERROR: No se pudo obtener config"
                }
                print(f"[POST] ✗ {hostname} error")
    
    with open(POST_DEPLOYMENT_FILE, "w") as f:
        json.dump(post_configs, f, indent=2)
    print(f"\n✓ Configuraciones POST guardadas en {POST_DEPLOYMENT_FILE}\n")
    
    # Comparar
    print("Analizando diferencias...")
    for device in devices:
        hostname = device["hostname"]
        
        pre_config = pre_configs.get(hostname, {}).get("running_config", "")
        post_config = post_configs.get(hostname, {}).get("running_config", "")
        pre_status = pre_configs.get(hostname, {}).get("status", "UNKNOWN")
        post_status = post_configs.get(hostname, {}).get("status", "UNKNOWN")
        
        if pre_status != "OK" or post_status != "OK":
            comparison_results[hostname] = {
                "status": "ERROR",
                "pre_status": pre_status,
                "post_status": post_status,
                "comparison": None
            }
            continue
        
        comparison_results[hostname] = {
            "status": "OK",
            "pre_status": pre_status,
            "post_status": post_status,
            "comparison": analyzer.compare_configs(pre_config, post_config)
        }
    
    print("✓ Análisis completado\n")
    return comparison_results


# ============================================================
# OPCIÓN C: BUSCAR COMANDOS
# ============================================================

def option_c_search_commands(devices: List[Dict], connector: DeviceConnector,
                            analyzer: ConfigAnalyzer) -> Dict:
    """
    OPCIÓN C: Busca comandos específicos en configuraciones
    """
    print("\n" + "=" * 80)
    print("OPCIÓN C: BUSCAR COMANDOS ESPECÍFICOS")
    print("=" * 80 + "\n")
    
    search_results = {}
    
    # Cargar configuraciones (usar las capturadas o POST-despliegue)
    configs = {}
    try:
        with open(POST_DEPLOYMENT_FILE, "r") as f:
            post_data = json.load(f)
            configs = post_data
        print(f"Usando configuraciones POST-despliegue\n")
    except:
        print("Capturando configuraciones para búsqueda...\n")
        for device in devices:
            hostname = device["hostname"]
            print(f"Conectando a {hostname}...")
            
            connection = connector.connect(hostname)
            if connection:
                config = connector.get_running_config(connection)
                connector.disconnect(connection)
                
                if config:
                    configs[hostname] = {
                        "timestamp": datetime.now().isoformat(),
                        "running_config": config,
                        "status": "OK"
                    }
                    print(f"✓ {hostname}")
                else:
                    configs[hostname] = {
                        "timestamp": datetime.now().isoformat(),
                        "running_config": None,
                        "status": "ERROR"
                    }
                    print(f"✗ {hostname}")
    
    # Buscar comandos
    print("\nBuscando comandos...\n")
    for device in devices:
        hostname = device["hostname"]
        device_type = device["device_type"]
        
        config = configs.get(hostname, {}).get("running_config", "")
        
        if not config:
            search_results[hostname] = {
                "device_type": device_type,
                "status": "ERROR",
                "search": None
            }
            continue
        
        # Seleccionar comandos según tipo
        commands = ROUTER_COMMANDS if device_type == "router" else SWITCH_COMMANDS
        
        search_results[hostname] = {
            "device_type": device_type,
            "status": "OK",
            "search": analyzer.search_commands(config, commands)
        }
    
    print("✓ Búsqueda completada\n")
    return search_results


# ============================================================
# OPCIÓN D: GENERAR REPORTE INTEGRADO
# ============================================================

def option_d_generate_integrated_report(devices: List[Dict],
                                       comparison_results: Dict,
                                       search_results: Dict) -> Tuple[str, str]:
    """
    OPCIÓN D: Genera reporte integrado en TXT
    Incluye: Inventario + Comparaciones + Búsquedas
    """
    print("\n" + "=" * 80)
    print("OPCIÓN D: GENERAR REPORTE INTEGRADO EN TXT")
    print("=" * 80 + "\n")
    
    report_gen = ReportGenerator(MASTER_REPORT_FILE, INVENTORY_DETAILED_FILE)
    
    # ========== SECCIÓN 1: INVENTARIO ==========
    print("Generando sección de Inventario...")
    inventory_content = report_gen.generate_inventory_section(devices)
    
    report_gen.add_section("INVENTARIO DE DISPOSITIVOS", inventory_content)
    
    routers = len([d for d in devices if d.get("device_type") == "router"])
    switches = len([d for d in devices if d.get("device_type") == "switch"])
    
    stats_content = report_gen.generate_statistics_section(devices, routers, switches)
    report_gen.add_section("ESTADÍSTICAS GENERALES", stats_content)
    
    # Guardar inventario separado
    report_gen.save_inventory_file(inventory_content)
    
    # ========== SECCIÓN 2: COMPARACIÓN PRE vs POST ==========
    if comparison_results:
        print("Generando sección de Comparación PRE vs POST...")
        report_gen.add_section(
            "COMPARACIÓN DE CONFIGURACIONES PRE vs POST DESPLIEGUE",
            f"Dispositivos analizados: {len(comparison_results)}"
        )
        
        for hostname, result in sorted(comparison_results.items()):
            report_gen.add_subsection(f"Dispositivo: {hostname}")
            
            content = []
            content.append(f"Estado Pre-Despliegue: {result['pre_status']}")
            content.append(f"Estado Post-Despliegue: {result['post_status']}")
            
            if result["status"] == "ERROR":
                content.append("Estado: ERROR - No se pudieron capturar configuraciones")
            else:
                comparison = result["comparison"]
                content.append(f"Líneas Pre-Despliegue: {comparison['pre_lines']}")
                content.append(f"Líneas Post-Despliegue: {comparison['post_lines']}")
                content.append(f"Total de cambios: {comparison['total_changes']}\n")
                
                if comparison["added"]:
                    content.append("LÍNEAS AGREGADAS:")
                    for line in comparison["added"][:30]:
                        content.append(f"  + {line}")
                    if len(comparison["added"]) > 30:
                        content.append(f"  ... y {len(comparison['added']) - 30} líneas más")
                else:
                    content.append("LÍNEAS AGREGADAS: Ninguna")
                
                content.append("")
                
                if comparison["removed"]:
                    content.append("LÍNEAS REMOVIDAS:")
                    for line in comparison["removed"][:30]:
                        content.append(f"  - {line}")
                    if len(comparison["removed"]) > 30:
                        content.append(f"  ... y {len(comparison['removed']) - 30} líneas más")
                else:
                    content.append("LÍNEAS REMOVIDAS: Ninguna")
            
            report_gen.report_content.append("\n".join(content))
            report_gen.report_content.append("")
    
    # ========== SECCIÓN 3: BÚSQUEDA DE COMANDOS ==========
    if search_results:
        print("Generando sección de Búsqueda de Comandos...")
        report_gen.add_section(
            "BÚSQUEDA DE COMANDOS ESPECÍFICOS",
            f"Dispositivos analizados: {len(search_results)}"
        )
        
        for hostname, result in sorted(search_results.items()):
            report_gen.add_subsection(f"Dispositivo: {hostname} ({result['device_type']})")
            
            content = []
            
            if result["status"] == "ERROR":
                content.append("Estado: ERROR - No se pudo acceder a la configuración")
            else:
                search = result["search"]
                total_commands = len(search["found"]) + len(search["not_found"])
                
                content.append(f"Total de comandos buscados: {total_commands}")
                content.append(f"Comandos encontrados: {search['total_found']}")
                content.append(f"Comandos no encontrados: {len(search['not_found'])}\n")
                
                if search["found"]:
                    content.append("COMANDOS ENCONTRADOS [OK]:")
                    for cmd in search["found"]:
                        content.append(f"  ✓ {cmd}")
                else:
                    content.append("COMANDOS ENCONTRADOS [OK]: Ninguno")
                
                content.append("")
                
                if search["not_found"]:
                    content.append("COMANDOS NO ENCONTRADOS [X]:")
                    for cmd in search["not_found"]:
                        content.append(f"  ✗ {cmd}")
                else:
                    content.append("COMANDOS NO ENCONTRADOS [X]: Ninguno")
            
            report_gen.report_content.append("\n".join(content))
            report_gen.report_content.append("")
    
    # ========== SECCIÓN 4: RESUMEN FINAL ==========
    print("Generando sección de Resumen Final...")
    
    report_gen.add_section("RESUMEN FINAL Y EVIDENCIAS")
    
    summary = []
    summary.append(f"Fecha y hora de generación: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    summary.append(f"Total de dispositivos procesados: {len(devices)}")
    summary.append(f"Topología: {TOPOLOGY_FILE}")
    summary.append("")
    summary.append("ARCHIVOS GENERADOS:")
    summary.append(f"  1. {MASTER_REPORT_FILE} - Reporte maestro integrado")
    summary.append(f"  2. {INVENTORY_DETAILED_FILE} - Inventario detallado")
    summary.append(f"  3. {PRE_DEPLOYMENT_FILE} - Configuraciones PRE")
    summary.append(f"  4. {POST_DEPLOYMENT_FILE} - Configuraciones POST")
    summary.append("")
    summary.append("PRÓXIMOS PASOS:")
    summary.append("  • Validar los cambios aplicados")
    summary.append("  • Ejecutar playbooks de validación NAPALM")
    summary.append("  • Documentar resultados en presentación")
    
    report_gen.report_content.append("\n".join(summary))
    
    # Guardar reporte
    report_gen.save_master_report()
    
    print(f"✓ Reporte maestro guardado: {MASTER_REPORT_FILE}")
    print(f"✓ Inventario detallado guardado: {INVENTORY_DETAILED_FILE}\n")
    
    return MASTER_REPORT_FILE, INVENTORY_DETAILED_FILE


# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================

def main():
    """Orquesta el flujo completo del script"""
    
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "  AUTOMATIZACIÓN Y PROGRAMABILIDAD DE REDES - LABORATORIO MPLS L3VPN".center(78) + "║")
    print("║" + "  SUITE DE AUTOMATIZACIÓN INTEGRADA (OPCIÓN D)".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "=" * 78 + "╝\n")
    
    # ========== PASO 1: Cargar topología ==========
    print("[PASO 1] Cargando topología...")
    topology_manager = TopologyManager(TOPOLOGY_FILE)
    if not topology_manager.load_topology():
        print("Abortando debido a error en topología")
        return
    
    # ========== PASO 2: Obtener dispositivos ==========
    print("[PASO 2] Obteniendo dispositivos de la topología...")
    devices = topology_manager.get_cisco_devices()
    if not devices:
        print("Error: No se encontraron dispositivos")
        return
    
    print(f"✓ {len(devices)} dispositivos encontrados\n")
    
    # ========== PASO 3: OPCIÓN A ==========
    option_a_devices = option_a_generate_inventory(topology_manager)
    
    # ========== PASO 4: Obtener credenciales ==========
    print("\n[CREDENCIALES] Ingrese credenciales SSH:")
    username = input("  Usuario SSH: ")
    password = getpass("  Contraseña SSH: ")
    print()
    
    connector = DeviceConnector(username, password)
    analyzer = ConfigAnalyzer()
    
    # ========== PASO 5: OPCIÓN B ==========
    comparison_results = option_b_compare_configs(devices, connector, analyzer)
    
    # ========== PASO 6: OPCIÓN C ==========
    search_results = option_c_search_commands(devices, connector, analyzer)
    
    # ========== PASO 7: OPCIÓN D ==========
    master_report, inventory_report = option_d_generate_integrated_report(
        devices,
        comparison_results,
        search_results
    )
    
    # ========== RESUMEN FINAL ==========
    print("\n" + "=" * 80)
    print("PROCESO COMPLETADO EXITOSAMENTE")
    print("=" * 80)
    print(f"\n✓ Reportes generados:")
    print(f"  1. {master_report} - Reporte integrado completo")
    print(f"  2. {inventory_report} - Inventario separado")
    print(f"  3. {PRE_DEPLOYMENT_FILE} - Configuraciones pre-despliegue")
    print(f"  4. {POST_DEPLOYMENT_FILE} - Configuraciones post-despliegue")
    print("\n✓ Próximos pasos:")
    print("  • Ejecutar playbooks de Ansible")
    print("  • Validar con NAPALM")
    print("  • Revisar reportes generados")
    print("\n")


# ============================================================
# PUNTO DE ENTRADA
# ============================================================

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n✗ Proceso interrumpido por el usuario")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error inesperado: {e}")
        logger.exception("Excepción no manejada")
        sys.exit(1)