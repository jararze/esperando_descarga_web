from flask import Flask, jsonify, send_file, Response, request
from flask_restx import Api, Resource, fields, Namespace
from flask_cors import CORS
import os
import pandas as pd
import requests
from datetime import datetime, timedelta
import logging
import threading
import time

# Crear app Flask
app = Flask(__name__)
CORS(app)
print("Flask app creada exitosamente")

# Configuración
app.config.update({
    'SECRET_KEY': os.environ.get('SECRET_KEY', 'tu-clave-secreta-development'),
    'DB_HOST': os.environ.get('DB_HOST', '159.203.123.109'),
    'DB_USER': os.environ.get('DB_USER', 'hnsrqkzfpr'),
    'DB_PASSWORD': os.environ.get('DB_PASSWORD', 'FdF6rJB6Ma'),
    'DB_DATABASE': os.environ.get('DB_DATABASE', 'hnsrqkzfpr'),
    'API_TOKEN': os.environ.get('API_TOKEN', 'bltrck2021_454fd3d'),
    'EXCEL_PATH': os.environ.get('EXCEL_PATH', 'GEOCERCAS_CBN.xlsx'),
    'HISTORICAL_PATH': os.environ.get('HISTORICAL_PATH', 'DataGrid.xlsx')
})

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API con Swagger
api = Api(
    app,
    version='2.0',
    title='Sistema de Tracking Completo - CBN',
    description='API REST completa con geocercas, alertas y reportes Excel',
    doc='/docs/',
    prefix='/api'
)

# Namespaces
tracking_ns = Namespace('tracking', description='Tracking avanzado de camiones')
alerts_ns = Namespace('alerts', description='Sistema de alertas por tiempo de espera')
reports_ns = Namespace('reports', description='Generación de reportes Excel completos')
geocercas_ns = Namespace('geocercas', description='Gestión de geocercas')

api.add_namespace(tracking_ns)
api.add_namespace(alerts_ns)
api.add_namespace(reports_ns)
api.add_namespace(geocercas_ns)

# Nuevos modelos para el mapa
map_stats_model = api.model('MapStats', {
    'total_trucks': fields.Integer(description='Total de camiones'),
    'by_alert_level': fields.Raw(description='Distribución por nivel de alerta'),
    'by_geocerca': fields.Raw(description='Distribución por geocerca'),
    'by_estado': fields.Raw(description='Distribución por estado'),
    'avg_progress': fields.Float(description='Progreso promedio'),
    'in_geocercas': fields.Integer(description='Camiones en geocercas'),
    'timestamp': fields.String(description='Timestamp de generación')
})

geojson_feature_model = api.model('GeoJSONFeature', {
    'type': fields.String(description='Tipo de feature'),
    'geometry': fields.Raw(description='Geometría del punto'),
    'properties': fields.Raw(description='Propiedades del camión')
})

geojson_model = api.model('GeoJSON', {
    'type': fields.String(description='Tipo de colección'),
    'features': fields.List(fields.Nested(geojson_feature_model), description='Lista de features')
})

# Modelos para sistema de alertas
alert_config_model = api.model('AlertConfiguration', {
    'thresholds': fields.Raw(description='Umbrales de tiempo para alertas'),
    'notification_settings': fields.Raw(description='Configuración de notificaciones'),
    'monitoring': fields.Raw(description='Configuración de monitoreo')
})

alert_dashboard_model = api.model('AlertDashboard', {
    'summary': fields.Raw(description='Resumen de alertas'),
    'alerts_by_destination': fields.Raw(description='Alertas por destino'),
    'hourly_trends': fields.List(fields.Raw(), description='Tendencias por hora'),
    'critical_alerts_detailed': fields.List(fields.Raw(), description='Alertas críticas detalladas'),
    'executive_summary': fields.Raw(description='Resumen ejecutivo'),
    'recommendations': fields.List(fields.Raw(), description='Recomendaciones'),
    'timestamp': fields.String(description='Timestamp de generación')
})

notification_model = api.model('Notification', {
    'id': fields.String(description='ID de notificación'),
    'type': fields.String(description='Tipo de notificación'),
    'priority': fields.String(description='Prioridad'),
    'message': fields.String(description='Mensaje'),
    'created_at': fields.String(description='Fecha de creación'),
    'status': fields.String(description='Estado')
})

# Namespace para funcionalidades del mapa
map_ns = Namespace('map', description='Funcionalidades del mapa interactivo')
api.add_namespace(map_ns)

# Modelos Swagger completos
truck_complete_model = api.model('TruckComplete', {
    'patente': fields.String(required=True, description='Patente del camión'),
    'planilla': fields.String(description='Número de planilla'),
    'status': fields.String(description='Estado actual (SALIDA, LLEGADA, etc.)'),
    'deposito_origen': fields.String(description='Depósito de origen'),
    'deposito_destino': fields.String(description='Depósito de destino'),
    'producto': fields.String(description='Producto transportado'),
    'latitude': fields.Float(description='Latitud actual'),
    'longitude': fields.Float(description='Longitud actual'),
    'velocidad_kmh': fields.Float(description='Velocidad en km/h'),
    'en_docks': fields.String(description='Estado en DOCKS'),
    'en_track_trace': fields.String(description='Estado en TRACK AND TRACE'),
    'en_cbn': fields.String(description='Estado en CBN'),
    'en_ciudades': fields.String(description='Estado en CIUDADES'),
    'porcentaje_entrega': fields.Float(description='Porcentaje de progreso (0-100)'),
    'estado_entrega': fields.String(description='Estado detallado de entrega'),
    'tiempo_espera_minutos': fields.Integer(description='Minutos esperando descarga'),
    'tiempo_espera_horas': fields.Float(description='Horas esperando descarga'),
    'estado_descarga': fields.String(description='Estado específico de descarga'),
    'alert_level': fields.String(description='Nivel de alerta (NORMAL, ATTENTION, WARNING, CRITICAL)'),
    'inicio_espera': fields.String(description='Fecha/hora inicio de espera')
})

alert_complete_model = api.model('AlertComplete', {
    'patente': fields.String(description='Patente del camión'),
    'planilla': fields.String(description='Número de planilla'),
    'deposito_destino': fields.String(description='Destino'),
    'horas_espera': fields.Float(description='Horas esperando'),
    'estado_descarga': fields.String(description='Estado de descarga'),
    'alert_level': fields.String(description='Nivel de alerta'),
    'inicio_espera': fields.String(description='Inicio de espera'),
    'status': fields.String(description='Status del camión')
})

geocerca_model = api.model('Geocerca', {
    'grupo': fields.String(description='Grupo de geocerca'),
    'nombre': fields.String(description='Nombre de la geocerca'),
    'activa': fields.Boolean(description='Si está activa'),
    'camiones_dentro': fields.Integer(description='Camiones actualmente dentro')
})

# Variable global para el servicio
tracking_service_complete = None


def init_complete_service():
    """Inicializa el servicio de tracking completo con manejo de errores"""
    global tracking_service_complete

    print("Iniciando servicio completo...")

    try:
        config = {
            'source_db': {
                'host': app.config['DB_HOST'],
                'user': app.config['DB_USER'],
                'password': app.config['DB_PASSWORD'],
                'database': 'controllogistico.v1',
                'charset': 'utf8mb4'
            },
            'target_db': {
                'host': app.config['DB_HOST'],
                'user': app.config['DB_USER'],
                'password': app.config['DB_PASSWORD'],
                'database': app.config['DB_DATABASE'],  # Usar la misma BD o crear otra
                'charset': 'utf8mb4'
            },
            'api': {
                'base_url': 'https://gestiondeflota.boltrack.net/integracionapi',
                'token': app.config['API_TOKEN']
            },
            'excel_path': app.config['EXCEL_PATH'],
            'historical_path': app.config['HISTORICAL_PATH']
        }

        # Importar con manejo de errores
        try:
            from truck_tracking_web_complete import TruckTrackingWebServiceComplete
            tracking_service_complete = TruckTrackingWebServiceComplete(config)
            logger.info("Servicio completo inicializado correctamente")
            print("Servicio completo inicializado correctamente")
        except ImportError as e:
            logger.error(f"Error importando TruckTrackingWebServiceComplete: {e}")
            print(f"Error importando servicio: {e}")
            tracking_service_complete = None
        except Exception as e:
            logger.error(f"Error inicializando servicio: {e}")
            print(f"Error inicializando servicio: {e}")
            tracking_service_complete = None

    except Exception as e:
        logger.error(f"Error general en init_complete_service: {e}")
        print(f"Error general en init_complete_service: {e}")
        tracking_service_complete = None


@app.route('/health')
def health_check():
    """Verificación básica de salud"""
    return {
        "status": "Flask funcionando correctamente",
        "timestamp": datetime.now().isoformat(),
        "routes_registered": len(app.url_map._rules),
        "service_initialized": tracking_service_complete is not None
    }

@app.route('/test')
def test():
    """Prueba simple"""
    return "La aplicación Flask funciona correctamente!"

@app.route('/simple')
def simple():
    """Prueba con HTML"""
    return """
    <html>
    <head><title>Sistema Funcionando</title></head>
    <body style="font-family: Arial; text-align: center; padding: 50px;">
        <h1 style="color: #667eea;">Sistema Funcionando</h1>
        <p>Flask está activo y funcionando correctamente</p>
        <p><strong>Timestamp:</strong> """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """</p>
        <a href="/" style="color: #667eea;">Volver al inicio</a>
    </body>
    </html>
    """

@app.route('/debug/routes')
def show_routes():
    """Muestra todas las rutas registradas"""
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': list(rule.methods),
            'rule': rule.rule
        })
    return {
        'total_routes': len(routes),
        'routes': routes,
        'timestamp': datetime.now().isoformat()
    }

@app.route('/')
def home():
    """Página principal con diseño moderno actualizado"""
    return f"""
    <html>
    <head>
        <title>Sistema de Tracking Completo - CBN</title>
        <style>
            body {{ 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; 
                margin: 0; 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                min-height: 100vh; 
            }}
            .container {{ 
                max-width: 1200px; 
                margin: 0 auto; 
                padding: 40px 20px; 
            }}
            .header {{ 
                text-align: center; 
                color: white; 
                margin-bottom: 50px; 
            }}
            .header h1 {{ 
                font-size: 3em; 
                margin: 0; 
                text-shadow: 2px 2px 4px rgba(0,0,0,0.3); 
            }}
            .header p {{ 
                font-size: 1.2em; 
                opacity: 0.9; 
                margin: 20px 0; 
            }}
            .cards {{ 
                display: grid; 
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); 
                gap: 30px; 
            }}
            .card {{ 
                background: white; 
                border-radius: 15px; 
                padding: 30px; 
                box-shadow: 0 10px 30px rgba(0,0,0,0.2); 
                transition: transform 0.3s ease; 
            }}
            .card:hover {{ 
                transform: translateY(-5px); 
            }}
            .card h3 {{ 
                color: #333; 
                margin: 0 0 15px 0; 
                font-size: 1.5em; 
            }}
            .card p {{ 
                color: #666; 
                line-height: 1.6; 
            }}
            .btn {{ 
                background: linear-gradient(45deg, #667eea, #764ba2); 
                color: white; 
                padding: 12px 24px; 
                text-decoration: none; 
                border-radius: 25px; 
                display: inline-block; 
                margin: 10px 5px; 
                transition: all 0.3s ease; 
            }}
            .btn:hover {{ 
                transform: translateY(-2px); 
                box-shadow: 0 5px 15px rgba(0,0,0,0.2); 
            }}
            .btn.primary {{ 
                background: linear-gradient(45deg, #11998e, #38ef7d); 
            }}
            .btn.danger {{ 
                background: linear-gradient(45deg, #ff6b6b, #ee5a52); 
            }}
            .btn.info {{ 
                background: linear-gradient(45deg, #4facfe, #00f2fe); 
            }}
            .btn.map {{ 
                background: linear-gradient(45deg, #667eea, #764ba2); 
                font-size: 1.1em;
                padding: 15px 30px;
            }}
            .status {{ 
                display: flex; 
                align-items: center; 
                margin: 15px 0; 
            }}
            .status-dot {{ 
                width: 12px; 
                height: 12px; 
                border-radius: 50%; 
                margin-right: 10px; 
                background: #38ef7d; 
            }}
            .features {{ 
                display: grid; 
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
                gap: 15px; 
                margin: 20px 0; 
            }}
            .feature {{ 
                background: #f8f9fa; 
                padding: 15px; 
                border-radius: 8px; 
                text-align: center; 
            }}
            .feature-icon {{ 
                font-size: 2em; 
                margin-bottom: 10px; 
            }}
            .highlight {{ 
                border: 3px solid #38ef7d; 
                background: linear-gradient(135deg, #f8f9ff, #e8f4fd); 
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚛 Sistema de Tracking Completo</h1>
                <p>Monitoreo avanzado de camiones con geocercas, alertas y reportes automáticos</p>
                <div class="status">
                    <div class="status-dot"></div>
                    <span>Sistema operativo - Última actualización: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</span>
                </div>
            </div>

            <div class="cards">
                <div class="card highlight">
                    <h3>🗺️ Mapa Interactivo NUEVO</h3>
                    <p>Dashboard avanzado con mapa en tiempo real, filtros inteligentes, geocercas visuales y tracking GPS interactivo</p>
                    <a href="/map-dashboard" class="btn map">🚀 Abrir Mapa Interactivo</a>
                </div>
                
                <div class="card highlight">
                    <h3>🚨 Dashboard de Alertas NUEVO</h3>
                    <p>Sistema avanzado de alertas con configuración personalizable, tendencias históricas, notificaciones automáticas y recomendaciones inteligentes</p>
                    <a href="/alerts-dashboard" class="btn map">🔥 Abrir Dashboard de Alertas</a>
                </div>

                <div class="card">
                    <h3>📖 Documentación API Completa</h3>
                    <p>Explora todos los endpoints: tracking avanzado, alertas automáticas, geocercas y reportes Excel completos</p>
                    <a href="/docs/" class="btn primary">🚀 Abrir Swagger UI Completo</a>
                </div>

                <div class="card">
                    <h3>📊 Dashboard Clásico</h3>
                    <p>Visualización completa con geocercas, alertas por tiempo de espera y métricas avanzadas</p>
                    <a href="/dashboard" class="btn info">🎯 Dashboard Clásico</a>
                </div>

                <div class="card">
                    <h3>🚨 Sistema de Alertas</h3>
                    <p>Monitoreo automático de tiempos de espera con alertas críticas, advertencias y atención</p>
                    <a href="/api/alerts/active" class="btn danger">⚠️ Alertas Activas</a>
                    <a href="/api/alerts/critical" class="btn danger">🚨 Críticas</a>
                </div>

                <div class="card">
                    <h3>📈 Reportes y Analytics</h3>
                    <p>Generación automática de reportes Excel con múltiples hojas, colores y análisis completo</p>
                    <a href="/api/reports/excel-complete" class="btn">📊 Generar Excel</a>
                    <a href="/api/tracking/stats-complete" class="btn">📈 Estadísticas</a>
                </div>

                <div class="card">
                    <h3>🗺️ Geocercas</h3>
                    <p>Sistema completo de geocercas: DOCKS, Track & Trace, CBN y Ciudades con porcentajes de entrega</p>
                    <a href="/api/geocercas/status" class="btn">🎯 Estado Geocercas</a>
                    <a href="/api/tracking/progress" class="btn">📊 Progreso Entregas</a>
                </div>

                <div class="card">
                    <h3>⚡ APIs Rápidas</h3>
                    <div class="features">
                        <div class="feature">
                            <div class="feature-icon">🚛</div>
                            <a href="/api/tracking/status-complete" class="btn">Tracking Completo</a>
                        </div>
                        <div class="feature">
                            <div class="feature-icon">📊</div>
                            <a href="/api/tracking/dashboard-stats" class="btn">Stats Dashboard</a>
                        </div>
                        <div class="feature">
                            <div class="feature-icon">⏱️</div>
                            <a href="/api/alerts/summary" class="btn">Resumen Alertas</a>
                        </div>
                        <div class="feature">
                            <div class="feature-icon">🔄</div>
                            <a href="/api/tracking/process" class="btn">Procesar Ahora</a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """

# ===============================
# ENDPOINTS DE TRACKING COMPLETO
# ===============================

@tracking_ns.route('/status-complete')
class TrackingStatusComplete(Resource):
    @tracking_ns.doc('get_tracking_status_complete')
    @tracking_ns.marshal_list_with(truck_complete_model)
    def get(self):
        """Obtiene estado completo de todos los camiones con geocercas y alertas"""
        try:
            if not tracking_service_complete:
                init_complete_service()

            data = tracking_service_complete.get_all_trucks_status_complete()
            return data, 200
        except Exception as e:
            api.abort(500, f"Error: {str(e)}")


@tracking_ns.route('/progress')
class DeliveryProgress(Resource):
    @tracking_ns.doc('get_delivery_progress')
    def get(self):
        """Obtiene progreso de entrega de todos los camiones"""
        try:
            if not tracking_service_complete:
                init_complete_service()

            trucks = tracking_service_complete.get_all_trucks_status_complete()
            progress_data = []

            for truck in trucks:
                progress_data.append({
                    'patente': truck['patente'],
                    'deposito_destino': truck['deposito_destino'],
                    'porcentaje_entrega': truck['porcentaje_entrega'],
                    'estado_entrega': truck['estado_entrega'],
                    'en_docks': truck['en_docks'] != 'NO',
                    'en_track_trace': truck['en_track_trace'] != 'NO',
                    'en_cbn': truck['en_cbn'] != 'NO',
                    'en_ciudades': truck['en_ciudades'] != 'NO'
                })

            return progress_data, 200
        except Exception as e:
            api.abort(500, f"Error: {str(e)}")


@tracking_ns.route('/dashboard-stats')
class DashboardStatsComplete(Resource):
    @tracking_ns.doc('get_dashboard_stats_complete')
    def get(self):
        """Obtiene estadísticas completas para dashboard avanzado"""
        try:
            if not tracking_service_complete:
                init_complete_service()

            stats = tracking_service_complete.get_dashboard_stats_complete()
            return stats, 200
        except Exception as e:
            api.abort(500, f"Error: {str(e)}")


@tracking_ns.route('/process')
class ProcessTrucksComplete(Resource):
    @tracking_ns.doc('trigger_complete_processing')
    def post(self):
        """Inicia procesamiento completo con geocercas y alertas"""
        try:
            if not tracking_service_complete:
                init_complete_service()

            # Ejecutar procesamiento completo en background
            thread = threading.Thread(target=tracking_service_complete.process_all_trucks_complete)
            thread.daemon = True
            thread.start()

            return {
                'message': 'Procesamiento completo iniciado en background',
                'status': 'started',
                'includes': [
                    'Geocercas (DOCKS, Track&Trace, CBN, Ciudades)',
                    'Cálculo de porcentajes de entrega',
                    'Tiempo de espera para descarga',
                    'Alertas automáticas',
                    'Actualización de BD completa'
                ]
            }, 202
        except Exception as e:
            api.abort(500, f"Error: {str(e)}")


# ===============================
# ENDPOINTS DE ALERTAS COMPLETAS
# ===============================

@alerts_ns.route('/active')
class ActiveAlertsComplete(Resource):
    @alerts_ns.doc('get_active_alerts_complete')
    @alerts_ns.marshal_list_with(alert_complete_model)
    def get(self):
        """Obtiene todas las alertas activas con detalles completos"""
        try:
            if not tracking_service_complete:
                init_complete_service()

            alerts = tracking_service_complete.get_active_alerts_complete()
            return alerts, 200
        except Exception as e:
            api.abort(500, f"Error: {str(e)}")


@alerts_ns.route('/critical')
class CriticalAlertsComplete(Resource):
    @alerts_ns.doc('get_critical_alerts_complete')
    @alerts_ns.marshal_list_with(alert_complete_model)
    def get(self):
        """Obtiene solo alertas críticas (>48h esperando)"""
        try:
            if not tracking_service_complete:
                init_complete_service()

            alerts = tracking_service_complete.get_critical_alerts_complete()
            return alerts, 200
        except Exception as e:
            api.abort(500, f"Error: {str(e)}")


@alerts_ns.route('/summary')
class AlertsSummaryComplete(Resource):
    @alerts_ns.doc('get_alerts_summary_complete')
    def get(self):
        """Obtiene resumen completo de alertas por nivel y tiempo"""
        try:
            if not tracking_service_complete:
                init_complete_service()

            summary = tracking_service_complete.get_alerts_summary_complete()
            return summary, 200
        except Exception as e:
            api.abort(500, f"Error: {str(e)}")


# ===============================
# ENDPOINTS DE REPORTES COMPLETOS
# ===============================

@reports_ns.route('/excel-complete')
class ExcelReportComplete(Resource):
    @reports_ns.doc('generate_excel_complete')
    def post(self):
        """Genera reporte Excel completo con múltiples hojas y colores automáticos"""
        try:
            if not tracking_service_complete:
                init_complete_service()

            excel_file = tracking_service_complete.generate_excel_report_complete()

            if excel_file and os.path.exists(excel_file):
                return send_file(
                    excel_file,
                    as_attachment=True,
                    download_name=f'tracking_completo_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx',
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
            else:
                api.abort(500, "Error generando archivo Excel completo")
        except Exception as e:
            api.abort(500, f"Error: {str(e)}")


# ===============================
# ENDPOINTS DE GEOCERCAS
# ===============================

@geocercas_ns.route('/status')
class GeocercasStatus(Resource):
    @geocercas_ns.doc('get_geocercas_status')
    @geocercas_ns.marshal_list_with(geocerca_model)
    def get(self):
        """Obtiene estado de todas las geocercas y camiones dentro"""
        try:
            if not tracking_service_complete:
                init_complete_service()

            status = tracking_service_complete.get_geocercas_status()
            return status, 200
        except Exception as e:
            api.abort(500, f"Error: {str(e)}")


@geocercas_ns.route('/distribution')
class GeocercasDistribution(Resource):
    @geocercas_ns.doc('get_geocercas_distribution')
    def get(self):
        """Obtiene distribución de camiones por geocerca"""
        try:
            if not tracking_service_complete:
                init_complete_service()

            distribution = tracking_service_complete.get_geocercas_distribution()
            return distribution, 200
        except Exception as e:
            api.abort(500, f"Error: {str(e)}")


# ===============================
# ENDPOINTS DEL MAPA INTERACTIVO
# ===============================

@map_ns.route('/trucks-geojson')
class TrucksGeoJSON(Resource):
    @map_ns.doc('get_trucks_geojson')
    @map_ns.marshal_with(geojson_model)
    def get(self):
        """Obtiene camiones en formato GeoJSON para mapas"""
        try:
            if not tracking_service_complete:
                init_complete_service()

            trucks = tracking_service_complete.get_all_trucks_status_complete()

            features = []
            for truck in trucks:
                if truck.get('latitude') and truck.get('longitude'):
                    feature = {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [truck['longitude'], truck['latitude']]
                        },
                        "properties": {
                            "patente": truck['patente'],
                            "planilla": truck.get('planilla', ''),
                            "status": truck.get('status', ''),
                            "deposito_destino": truck.get('deposito_destino', ''),
                            "alert_level": truck.get('alert_level', 'NORMAL'),
                            "porcentaje_entrega": truck.get('porcentaje_entrega', 0),
                            "estado_entrega": truck.get('estado_entrega', 'EN_TRANSITO'),
                            "tiempo_espera_horas": truck.get('tiempo_espera_horas', 0),
                            "velocidad_kmh": truck.get('velocidad_kmh', 0),
                            "en_docks": truck.get('en_docks', 'NO'),
                            "en_track_trace": truck.get('en_track_trace', 'NO'),
                            "en_cbn": truck.get('en_cbn', 'NO'),
                            "en_ciudades": truck.get('en_ciudades', 'NO'),
                            "timestamp": truck.get('timestamp', ''),
                            "producto": truck.get('producto', '')
                        }
                    }
                    features.append(feature)

            geojson = {
                "type": "FeatureCollection",
                "features": features
            }

            return geojson, 200

        except Exception as e:
            api.abort(500, f"Error generando GeoJSON: {str(e)}")


@map_ns.route('/stats-summary')
class MapStatsSummary(Resource):
    @map_ns.doc('get_map_stats_summary')
    @map_ns.marshal_with(map_stats_model)
    def get(self):
        """Obtiene estadísticas optimizadas para el mapa"""
        try:
            if not tracking_service_complete:
                init_complete_service()

            trucks = tracking_service_complete.get_all_trucks_status_complete()

            if not trucks:
                return {
                    'total_trucks': 0,
                    'by_alert_level': {},
                    'by_geocerca': {},
                    'by_estado': {},
                    'avg_progress': 0,
                    'in_geocercas': 0,
                    'timestamp': datetime.now().isoformat()
                }

            # Estadísticas por nivel de alerta
            by_alert = {}
            for truck in trucks:
                alert = truck.get('alert_level', 'NORMAL')
                by_alert[alert] = by_alert.get(alert, 0) + 1

            # Estadísticas por geocerca
            by_geocerca = {
                'docks': len([t for t in trucks if t.get('en_docks', 'NO') != 'NO']),
                'track_trace': len([t for t in trucks if t.get('en_track_trace', 'NO') != 'NO']),
                'cbn': len([t for t in trucks if t.get('en_cbn', 'NO') != 'NO']),
                'ciudades': len([t for t in trucks if t.get('en_ciudades', 'NO') != 'NO'])
            }

            # Estadísticas por estado de entrega
            by_estado = {}
            for truck in trucks:
                estado = truck.get('estado_entrega', 'EN_TRANSITO')
                by_estado[estado] = by_estado.get(estado, 0) + 1

            # Progreso promedio
            total_progress = sum(truck.get('porcentaje_entrega', 0) for truck in trucks)
            avg_progress = round(total_progress / len(trucks), 1) if trucks else 0

            return {
                'total_trucks': len(trucks),
                'by_alert_level': by_alert,
                'by_geocerca': by_geocerca,
                'by_estado': by_estado,
                'avg_progress': avg_progress,
                'in_geocercas': sum(by_geocerca.values()),
                'timestamp': datetime.now().isoformat()
            }, 200

        except Exception as e:
            api.abort(500, f"Error generando estadísticas: {str(e)}")


@app.route('/download/excel')
def download_excel():
    """Endpoint específico para descargar Excel desde navegador"""
    try:
        if not tracking_service_complete:
            init_complete_service()

        excel_file = tracking_service_complete.generate_excel_report_complete()

        if excel_file and os.path.exists(excel_file):
            return send_file(
                excel_file,
                as_attachment=True,
                download_name=f'tracking_completo_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx',
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        else:
            return "Error generando archivo Excel", 500
    except Exception as e:
        return f"Error: {str(e)}", 500


# ===============================
# DASHBOARD COMPLETO
# ===============================

@app.route('/dashboard')
def dashboard_complete():
    """Dashboard completo con todas las funcionalidades"""
    try:
        if not tracking_service_complete:
            init_complete_service()

        # Obtener datos completos
        trucks = tracking_service_complete.get_all_trucks_status_complete()
        alerts = tracking_service_complete.get_alerts_summary_complete()
        geocercas_dist = tracking_service_complete.get_geocercas_distribution()

        # Calcular métricas
        total_camiones = len(trucks)
        con_ubicacion = len([t for t in trucks if t.get('latitude') and t.get('longitude')])
        en_descarga = len([t for t in trucks if 'DESCARGA' in t.get('estado_entrega', '')])

        # Último update de BD
        ultimo_update_bd = tracking_service_complete.get_last_update_from_db()

        # Determinar si BD está atrasada
        def is_bd_outdated():
            try:
                if ultimo_update_bd in ["N/A", "Error"]:
                    return True

                now = datetime.now()
                ultimo_time = datetime.strptime(ultimo_update_bd, '%H:%M:%S').time()
                ultimo_datetime = datetime.combine(now.date(), ultimo_time)

                if ultimo_datetime > now:
                    ultimo_datetime = ultimo_datetime - timedelta(days=1)

                diff = now - ultimo_datetime
                return diff.total_seconds() > 7200  # 2 horas

            except:
                return True

        bd_outdated = is_bd_outdated()
        bd_class = "metric bd-update outdated" if bd_outdated else "metric bd-update"

        # Promedio de progreso
        promedio_progreso = sum(t.get('porcentaje_entrega', 0) for t in trucks) / max(total_camiones, 1)

        html = f"""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Dashboard Completo - Tracking CBN</title>
            <meta http-equiv="refresh" content="60">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    color: #333;
                }}
                .container {{
                    max-width: 1400px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    text-align: center;
                    color: white;
                    margin-bottom: 30px;
                }}
                .header h1 {{
                    font-size: 2.5em;
                    margin: 0;
                    text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
                }}
                .metrics {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                    gap: 20px;
                    margin: 30px 0;
                }}
                .metric {{
                    background: white;
                    padding: 25px;
                    border-radius: 15px;
                    text-align: center;
                    box-shadow: 0 8px 25px rgba(0,0,0,0.15);
                    transition: transform 0.3s ease;
                }}
                .metric:hover {{ transform: translateY(-5px); }}
                .metric h3 {{
                    margin: 0;
                    font-size: 2.5em;
                    color: #667eea;
                    font-weight: bold;
                }}
                .metric p {{
                    margin: 10px 0 0 0;
                    color: #666;
                    font-weight: 500;
                }}
                .metric.bd-update {{
                    border-left: 6px solid #28a745;
                }}
                .metric.bd-update h3 {{ color: #28a745; }}
                .metric.bd-update.outdated {{
                    border-left: 6px solid #dc3545;
                    background: #fff5f5;
                }}
                .metric.bd-update.outdated h3 {{ color: #dc3545; }}
                .metric.bd-update.outdated p {{ color: #721c24; font-weight: bold; }}
                .metric.alert-critical {{ border-left: 6px solid #dc3545; }}
                .metric.alert-critical h3 {{ color: #dc3545; }}
                .metric.progress {{ border-left: 6px solid #17a2b8; }}
                .metric.progress h3 {{ color: #17a2b8; }}

                .cards-section {{
                    display: grid;
                    grid-template-columns: 2fr 1fr;
                    gap: 30px;
                    margin: 30px 0;
                }}
                .card {{
                    background: white;
                    border-radius: 15px;
                    padding: 25px;
                    box-shadow: 0 8px 25px rgba(0,0,0,0.15);
                }}
                .card h3 {{
                    margin: 0 0 20px 0;
                    color: #333;
                    border-bottom: 2px solid #667eea;
                    padding-bottom: 10px;
                }}
                .progress-bars {{
                    display: grid;
                    gap: 15px;
                }}
                .progress-item {{
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    margin-bottom: 10px;
                }}
                .progress-bar {{
                    flex: 1;
                    height: 25px;
                    background: #f0f0f0;
                    border-radius: 12px;
                    overflow: hidden;
                    margin: 0 15px;
                }}
                .progress-fill {{
                    height: 100%;
                    background: linear-gradient(45deg, #667eea, #764ba2);
                    transition: width 0.3s ease;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: white;
                    font-weight: bold;
                    font-size: 0.9em;
                }}
                .alerts-list {{
                    max-height: 400px;
                    overflow-y: auto;
                }}
                .alert-item {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 12px;
                    margin: 8px 0;
                    border-radius: 8px;
                    font-size: 0.9em;
                }}
                .alert-critical {{ background: #fff5f5; border-left: 4px solid #dc3545; }}
                .alert-warning {{ background: #fff8e1; border-left: 4px solid #ff9800; }}
                .alert-attention {{ background: #e3f2fd; border-left: 4px solid #2196f3; }}
                .truck-table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 20px;
                }}
                .truck-table th,
                .truck-table td {{
                    padding: 12px;
                    text-align: left;
                    border-bottom: 1px solid #ddd;
                }}
                .truck-table th {{
                    background: #667eea;
                    color: white;
                    font-weight: bold;
                }}
                .truck-table tr:hover {{
                    background: #f8f9fa;
                }}
                .status-badge {{
                    padding: 4px 8px;
                    border-radius: 12px;
                    font-size: 0.8em;
                    font-weight: bold;
                }}
                .status-transito {{ background: #e3f2fd; color: #1976d2; }}
                .status-ciudad {{ background: #fff3e0; color: #f57c00; }}
                .status-descarga {{ background: #e8f5e8; color: #388e3c; }}
                .buttons {{
                    text-align: center;
                    margin: 30px 0;
                }}
                .btn {{
                    background: linear-gradient(45deg, #667eea, #764ba2);
                    color: white;
                    padding: 12px 24px;
                    text-decoration: none;
                    border-radius: 25px;
                    margin: 0 10px;
                    font-weight: bold;
                    transition: all 0.3s ease;
                }}
                .btn:hover {{
                    transform: translateY(-2px);
                    box-shadow: 0 5px 15px rgba(0,0,0,0.2);
                }}
                .btn.danger {{ background: linear-gradient(45deg, #ff6b6b, #ee5a52); }}
                .btn.success {{ background: linear-gradient(45deg, #11998e, #38ef7d); }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📊 Dashboard Completo - Sistema de Tracking</h1>
                    <p>Monitoreo avanzado con geocercas, alertas automáticas y reportes</p>
                </div>

                <div class="metrics">
                    <div class="metric">
                        <h3>{total_camiones}</h3>
                        <p>Total Camiones</p>
                    </div>
                    <div class="metric">
                        <h3>{con_ubicacion}</h3>
                        <p>Con Ubicación GPS</p>
                    </div>
                    <div class="metric">
                        <h3>{en_descarga}</h3>
                        <p>En Proceso Descarga</p>
                    </div>
                    <div class="{bd_class}">
                        <h3>{ultimo_update_bd}</h3>
                        <p>Último Update BD</p>
                    </div>
                    <div class="metric alert-critical">
                        <h3>{alerts.get('critical_count', 0)}</h3>
                        <p>Alertas Críticas</p>
                    </div>
                    <div class="metric progress">
                        <h3>{promedio_progreso:.1f}%</h3>
                        <p>Progreso Promedio</p>
                    </div>
                </div>

                <div class="cards-section">
                    <div class="card">
                        <h3>📊 Distribución por Geocercas</h3>
                        <div class="progress-bars">
        """

        # Agregar barras de progreso para geocercas
        geocerca_names = ['DOCKS', 'TRACK AND TRACE', 'CBN', 'CIUDADES']
        for geocerca in geocerca_names:
            count = geocercas_dist.get(geocerca.lower().replace(' ', '_'), 0)
            percentage = (count / max(total_camiones, 1)) * 100

            html += f"""
                            <div class="progress-item">
                                <span style="min-width: 120px; font-weight: bold;">{geocerca}:</span>
                                <div class="progress-bar">
                                    <div class="progress-fill" style="width: {percentage}%;">
                                        {count} ({percentage:.1f}%)
                                    </div>
                                </div>
                            </div>
            """

        html += """
                        </div>
                    </div>

                    <div class="card">
                        <h3>🚨 Alertas Activas</h3>
                        <div class="alerts-list">
        """

        # Mostrar alertas activas
        if alerts.get('total_waiting', 0) > 0:
            html += f"""
                            <div class="alert-item alert-critical">
                                <span><strong>Críticas (>48h)</strong></span>
                                <span>{alerts.get('critical_count', 0)} camiones</span>
                            </div>
                            <div class="alert-item alert-warning">
                                <span><strong>Advertencias (>8h)</strong></span>
                                <span>{alerts.get('warning_count', 0)} camiones</span>
                            </div>
                            <div class="alert-item alert-attention">
                                <span><strong>Atención (>4h)</strong></span>
                                <span>{alerts.get('attention_count', 0)} camiones</span>
                            </div>
            """
        else:
            html += '<div style="text-align: center; color: #28a745; font-weight: bold;">✅ No hay alertas activas</div>'

        html += """
                        </div>
                    </div>
                </div>

                <div class="card">
                    <h3>🚛 Camiones en Tiempo Real</h3>
                    <table class="truck-table">
                        <thead>
                            <tr>
                                <th>Patente</th>
                                <th>Estado Entrega</th>
                                <th>Destino</th>
                                <th>Progreso</th>
                                <th>Tiempo Espera</th>
                                <th>Geocercas</th>
                            </tr>
                        </thead>
                        <tbody>
        """

        # Mostrar camiones (limitado a primeros 15 para performance)
        for truck in trucks[:15]:
            estado = truck.get('estado_entrega', 'EN_TRANSITO')
            if 'TRANSITO' in estado:
                status_class = 'status-transito'
            elif 'CIUDAD' in estado or 'CENTRO' in estado:
                status_class = 'status-ciudad'
            else:
                status_class = 'status-descarga'

            tiempo_espera = truck.get('tiempo_espera_horas', 0)
            tiempo_str = f"{tiempo_espera:.1f}h" if tiempo_espera > 0 else "-"

            geocercas_activas = []
            for geo in ['en_docks', 'en_track_trace', 'en_cbn', 'en_ciudades']:
                if truck.get(geo, 'NO') != 'NO':
                    geocercas_activas.append(geo.replace('en_', '').upper())

            geocercas_str = ', '.join(geocercas_activas) if geocercas_activas else 'Ninguna'

            html += f"""
                            <tr>
                                <td><strong>{truck.get('patente', 'N/A')}</strong></td>
                                <td><span class="status-badge {status_class}">{estado}</span></td>
                                <td>{truck.get('deposito_destino', 'N/A')}</td>
                                <td>{truck.get('porcentaje_entrega', 0):.1f}%</td>
                                <td>{tiempo_str}</td>
                                <td>{geocercas_str}</td>
                            </tr>
            """

        if len(trucks) > 15:
            html += f"""
                            <tr>
                                <td colspan="6" style="text-align: center; color: #666; font-style: italic;">
                                    ... y {len(trucks) - 15} camiones más. <a href="/api/tracking/status-complete" style="color: #667eea;">Ver todos en JSON</a>
                                </td>
                            </tr>
            """

        html += """
                        </tbody>
                    </table>
                </div>

                <div class="buttons">
                    <a href="/docs/" class="btn">📖 API Completa (Swagger)</a>
                    <a href="/download/excel" class="btn success">📊 Generar Excel Completo</a>
                    <a href="/api/alerts/critical" class="btn danger">🚨 Ver Alertas Críticas</a>
                    <a href="/" class="btn">🏠 Inicio</a>
                </div>

                <div style="text-align: center; margin: 30px 0; color: white;">
                    <p><em>Se actualiza automáticamente cada 60 segundos</em></p>
                    <p>Sistema completo con geocercas, alertas automáticas y reportes Excel • Última actualización: {datetime.now().strftime('%H:%M:%S')}</p>
                </div>
            </div>
        </body>
        </html>
        """

        return Response(html, mimetype='text/html')

    except Exception as e:
        logger.error(f"Error en dashboard completo: {e}")
        return f"""
        <html>
        <head><title>Error - Dashboard Completo</title></head>
        <body style="font-family: Arial; padding: 40px; background: #f5f5f5;">
            <div style="background: white; padding: 30px; border-radius: 10px; max-width: 600px; margin: 0 auto;">
                <h1 style="color: #dc3545;">⚠️ Error en Dashboard Completo</h1>
                <p><strong>Detalle del error:</strong> {str(e)}</p>
                <p><a href="/" style="color: #007bff;">🏠 Volver al inicio</a></p>
            </div>
        </body>
        </html>
        """, 500


# ===============================
# ENDPOINTS SISTEMA DE ALERTAS AVANZADO
# ===============================

@app.route('/alerts-dashboard')
def alerts_dashboard():
    """Dashboard avanzado de alertas con múltiples vistas"""
    return '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Dashboard de Alertas - CBN Tracking</title>

        <!-- Bootstrap 5 -->
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">

        <!-- Font Awesome -->
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">

        <!-- Chart.js -->
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                background: #f8f9fa;
                margin: 0;
                padding: 0;
            }

            .header-alerts {
                background: linear-gradient(135deg, #dc3545 0%, #fd7e14 100%);
                color: white;
                padding: 20px 0;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }

            .header-alerts h1 {
                margin: 0;
                font-size: 2rem;
                font-weight: bold;
            }

            .alert-stat-card {
                background: white;
                border-radius: 15px;
                padding: 25px;
                text-align: center;
                box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                transition: transform 0.3s ease;
                margin-bottom: 20px;
                border-left: 5px solid;
            }

            .alert-stat-card:hover {
                transform: translateY(-5px);
                box-shadow: 0 8px 25px rgba(0,0,0,0.15);
            }

            .alert-stat-card.critical {
                border-left-color: #dc3545;
            }

            .alert-stat-card.warning {
                border-left-color: #ffc107;
            }

            .alert-stat-card.attention {
                border-left-color: #17a2b8;
            }

            .alert-stat-card.info {
                border-left-color: #6c757d;
            }

            .stat-number {
                font-size: 3rem;
                font-weight: bold;
                margin: 0;
                line-height: 1;
            }

            .stat-number.critical { color: #dc3545; }
            .stat-number.warning { color: #ffc107; }
            .stat-number.attention { color: #17a2b8; }
            .stat-number.info { color: #6c757d; }

            .stat-label {
                font-size: 1rem;
                color: #666;
                margin: 10px 0 0 0;
            }

            .dashboard-section {
                background: white;
                border-radius: 15px;
                padding: 25px;
                margin-bottom: 25px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            }

            .section-title {
                font-size: 1.5rem;
                font-weight: bold;
                color: #333;
                margin: 0 0 20px 0;
                border-bottom: 2px solid #dc3545;
                padding-bottom: 10px;
            }

            .alert-item {
                background: #f8f9fa;
                border-radius: 10px;
                padding: 20px;
                margin: 15px 0;
                border-left: 5px solid;
                transition: all 0.3s ease;
                cursor: pointer;
            }

            .alert-item:hover {
                background: #e9ecef;
                transform: translateX(5px);
            }

            .alert-item.critical {
                border-left-color: #dc3545;
                background: linear-gradient(90deg, #fff5f5 0%, #f8f9fa 100%);
            }

            .alert-item.warning {
                border-left-color: #ffc107;
                background: linear-gradient(90deg, #fffbf0 0%, #f8f9fa 100%);
            }

            .alert-item.attention {
                border-left-color: #17a2b8;
                background: linear-gradient(90deg, #f0f9ff 0%, #f8f9fa 100%);
            }

            .alert-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 10px;
            }

            .alert-title {
                font-size: 1.2rem;
                font-weight: bold;
                color: #333;
                margin: 0;
            }

            .alert-badge {
                padding: 5px 15px;
                border-radius: 20px;
                font-size: 0.8rem;
                font-weight: bold;
                text-transform: uppercase;
            }

            .alert-badge.critical {
                background: #dc3545;
                color: white;
            }

            .alert-badge.warning {
                background: #ffc107;
                color: #212529;
            }

            .alert-badge.attention {
                background: #17a2b8;
                color: white;
            }

            .alert-details {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
                margin-top: 15px;
            }

            .alert-detail-item {
                display: flex;
                align-items: center;
                font-size: 0.9rem;
                color: #666;
            }

            .alert-detail-item i {
                margin-right: 8px;
                color: #999;
                width: 16px;
            }

            .priority-indicator {
                width: 20px;
                height: 20px;
                border-radius: 50%;
                display: inline-block;
                margin-right: 10px;
            }

            .priority-high {
                background: #dc3545;
                box-shadow: 0 0 10px rgba(220, 53, 69, 0.5);
                animation: pulse-red 2s infinite;
            }

            .priority-medium {
                background: #ffc107;
            }

            .priority-low {
                background: #28a745;
            }

            @keyframes pulse-red {
                0% { box-shadow: 0 0 0 0 rgba(220, 53, 69, 0.7); }
                70% { box-shadow: 0 0 0 10px rgba(220, 53, 69, 0); }
                100% { box-shadow: 0 0 0 0 rgba(220, 53, 69, 0); }
            }

            .chart-container {
                position: relative;
                height: 300px;
                margin: 20px 0;
            }

            .recommendations-list {
                list-style: none;
                padding: 0;
            }

            .recommendation-item {
                background: #f8f9fa;
                border-radius: 8px;
                padding: 15px;
                margin: 10px 0;
                border-left: 4px solid #17a2b8;
            }

            .recommendation-item.urgent {
                border-left-color: #dc3545;
                background: #fff5f5;
            }

            .recommendation-item.attention {
                border-left-color: #ffc107;
                background: #fffbf0;
            }

            .executive-summary {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border-radius: 15px;
                padding: 25px;
                margin-bottom: 25px;
            }

            .executive-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 20px;
                margin-top: 20px;
            }

            .executive-item {
                text-align: center;
                background: rgba(255,255,255,0.1);
                border-radius: 10px;
                padding: 15px;
            }

            .executive-number {
                font-size: 2rem;
                font-weight: bold;
                margin: 0;
            }

            .executive-label {
                font-size: 0.9rem;
                opacity: 0.9;
                margin: 5px 0 0 0;
            }

            .loading-overlay {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0,0,0,0.5);
                display: flex;
                justify-content: center;
                align-items: center;
                z-index: 9999;
            }

            .loading-content {
                background: white;
                padding: 30px;
                border-radius: 15px;
                text-align: center;
            }

            .auto-refresh-indicator {
                position: fixed;
                top: 20px;
                right: 20px;
                background: rgba(220, 53, 69, 0.9);
                color: white;
                padding: 10px 20px;
                border-radius: 25px;
                font-size: 0.9rem;
                z-index: 1000;
                box-shadow: 0 2px 10px rgba(0,0,0,0.2);
            }

            .refresh-dot {
                display: inline-block;
                width: 8px;
                height: 8px;
                background: white;
                border-radius: 50%;
                margin-right: 8px;
                animation: pulse-white 2s infinite;
            }

            @keyframes pulse-white {
                0% { opacity: 1; }
                50% { opacity: 0.5; }
                100% { opacity: 1; }
            }

            .filter-tabs {
                display: flex;
                gap: 10px;
                margin-bottom: 20px;
                border-bottom: 2px solid #e9ecef;
                padding-bottom: 10px;
            }

            .filter-tab {
                padding: 10px 20px;
                border: 2px solid transparent;
                border-radius: 25px;
                background: #f8f9fa;
                color: #666;
                cursor: pointer;
                transition: all 0.3s ease;
                font-weight: 500;
            }

            .filter-tab.active {
                background: #dc3545;
                color: white;
                transform: translateY(-2px);
            }

            .filter-tab:hover {
                background: #e9ecef;
                transform: translateY(-1px);
            }

            .filter-tab.active:hover {
                background: #c82333;
            }
        </style>
    </head>
    <body>
        <!-- Loading overlay -->
        <div id="loading-overlay" class="loading-overlay">
            <div class="loading-content">
                <div class="spinner-border text-danger" role="status" style="width: 3rem; height: 3rem;">
                    <span class="visually-hidden">Cargando...</span>
                </div>
                <p class="mt-3 mb-0">Cargando dashboard de alertas...</p>
            </div>
        </div>

        <!-- Auto-refresh indicator -->
        <div class="auto-refresh-indicator">
            <span class="refresh-dot"></span>
            <span id="refresh-status">Actualizando cada 30s</span>
        </div>

        <!-- Header -->
        <div class="header-alerts">
            <div class="container-fluid">
                <div class="row align-items-center">
                    <div class="col-md-6">
                        <h1><i class="fas fa-exclamation-triangle"></i> Dashboard de Alertas</h1>
                        <p class="mb-0">Monitoreo avanzado de alertas críticas y tiempos de espera</p>
                    </div>
                    <div class="col-md-6 text-end">
                        <span id="last-update"
                        <span id="last-update" class="badge bg-light text-dark">Cargando...</span>
                       <button class="btn btn-light btn-sm ms-2" onclick="refreshAlerts()">
                           <i class="fas fa-sync-alt"></i> Actualizar
                       </button>
                       <a href="/map-dashboard" class="btn btn-outline-light btn-sm ms-2">
                           <i class="fas fa-map"></i> Ver Mapa
                       </a>
                       <a href="/" class="btn btn-outline-light btn-sm ms-2">
                           <i class="fas fa-home"></i> Inicio
                       </a>
                   </div>
               </div>
           </div>
       </div>
       
       <div class="container-fluid">
           <!-- Executive Summary -->
           <div class="executive-summary">
               <h3><i class="fas fa-chart-line"></i> Resumen Ejecutivo</h3>
               <div class="executive-grid" id="executive-summary">
                   <!-- Se llena dinámicamente -->
               </div>
           </div>
           
           <!-- Stats Cards -->
           <div class="row">
               <div class="col-md-3">
                   <div class="alert-stat-card critical">
                       <div id="critical-count" class="stat-number critical">-</div>
                       <div class="stat-label">Alertas Críticas</div>
                       <small class="text-muted">Más de 48h esperando</small>
                   </div>
               </div>
               <div class="col-md-3">
                   <div class="alert-stat-card warning">
                       <div id="warning-count" class="stat-number warning">-</div>
                       <div class="stat-label">Advertencias</div>
                       <small class="text-muted">Más de 8h esperando</small>
                   </div>
               </div>
               <div class="col-md-3">
                   <div class="alert-stat-card attention">
                       <div id="attention-count" class="stat-number attention">-</div>
                       <div class="stat-label">Atención</div>
                       <small class="text-muted">Más de 4h esperando</small>
                   </div>
               </div>
               <div class="col-md-3">
                   <div class="alert-stat-card info">
                       <div id="total-waiting" class="stat-number info">-</div>
                       <div class="stat-label">Total Esperando</div>
                       <small class="text-muted">Todos los niveles</small>
                   </div>
               </div>
           </div>
           
           <div class="row">
               <!-- Critical Alerts Section -->
               <div class="col-md-8">
                   <div class="dashboard-section">
                       <div class="section-title">
                           <i class="fas fa-fire"></i> Alertas Críticas - Atención Inmediata
                       </div>
                       
                       <!-- Filter tabs -->
                       <div class="filter-tabs">
                           <div class="filter-tab active" data-filter="all">
                               <i class="fas fa-list"></i> Todas
                           </div>
                           <div class="filter-tab" data-filter="critical">
                               <i class="fas fa-exclamation-triangle"></i> Solo Críticas
                           </div>
                           <div class="filter-tab" data-filter="high-priority">
                               <i class="fas fa-star"></i> Alta Prioridad
                           </div>
                           <div class="filter-tab" data-filter="docks">
                               <i class="fas fa-warehouse"></i> En DOCKS
                           </div>
                       </div>
                       
                       <div id="critical-alerts-list">
                           <!-- Se llena dinámicamente -->
                       </div>
                   </div>
               </div>
               
               <!-- Recommendations Panel -->
               <div class="col-md-4">
                   <div class="dashboard-section">
                       <div class="section-title">
                           <i class="fas fa-lightbulb"></i> Recomendaciones
                       </div>
                       <ul id="recommendations-list" class="recommendations-list">
                           <!-- Se llena dinámicamente -->
                       </ul>
                   </div>
                   
                   <!-- Alerts by Destination -->
                   <div class="dashboard-section">
                       <div class="section-title">
                           <i class="fas fa-map-marker-alt"></i> Alertas por Destino
                       </div>
                       <div class="chart-container">
                           <canvas id="destinationChart"></canvas>
                       </div>
                   </div>
               </div>
           </div>
           
           <!-- Trends Section -->
           <div class="row">
               <div class="col-md-12">
                   <div class="dashboard-section">
                       <div class="section-title">
                           <i class="fas fa-chart-area"></i> Tendencias de Alertas (Últimas 24 horas)
                       </div>
                       <div class="chart-container" style="height: 400px;">
                           <canvas id="trendsChart"></canvas>
                       </div>
                   </div>
               </div>
           </div>
           
           <!-- Configuration Panel -->
           <div class="row">
               <div class="col-md-6">
                   <div class="dashboard-section">
                       <div class="section-title">
                           <i class="fas fa-cog"></i> Configuración de Alertas
                       </div>
                       <form id="alert-config-form">
                           <div class="row">
                               <div class="col-md-4">
                                   <label class="form-label">Atención (horas)</label>
                                   <input type="number" class="form-control" id="normal-hours" min="1" max="24" step="0.5">
                               </div>
                               <div class="col-md-4">
                                   <label class="form-label">Advertencia (horas)</label>
                                   <input type="number" class="form-control" id="warning-hours" min="1" max="48" step="0.5">
                               </div>
                               <div class="col-md-4">
                                   <label class="form-label">Crítico (horas)</label>
                                   <input type="number" class="form-control" id="critical-hours" min="12" max="168" step="0.5">
                               </div>
                           </div>
                           <div class="mt-3">
                               <button type="button" class="btn btn-primary" onclick="updateAlertConfig()">
                                   <i class="fas fa-save"></i> Guardar Configuración
                               </button>
                               <button type="button" class="btn btn-outline-secondary ms-2" onclick="resetAlertConfig()">
                                   <i class="fas fa-undo"></i> Restaurar
                               </button>
                           </div>
                       </form>
                   </div>
               </div>
               
               <div class="col-md-6">
                   <div class="dashboard-section">
                       <div class="section-title">
                           <i class="fas fa-bell"></i> Notificaciones
                       </div>
                       <div class="mb-3">
                           <div class="form-check form-switch">
                               <input class="form-check-input" type="checkbox" id="email-notifications" checked>
                               <label class="form-check-label" for="email-notifications">
                                   <i class="fas fa-envelope"></i> Notificaciones por Email
                               </label>
                           </div>
                       </div>
                       <div class="mb-3">
                           <div class="form-check form-switch">
                               <input class="form-check-input" type="checkbox" id="auto-escalation">
                               <label class="form-check-label" for="auto-escalation">
                                   <i class="fas fa-arrow-up"></i> Escalación Automática
                               </label>
                           </div>
                       </div>
                       <div class="mb-3">
                           <label class="form-label">Próxima escalación en:</label>
                           <div class="input-group">
                               <span class="input-group-text"><i class="fas fa-clock"></i></span>
                               <input type="text" class="form-control" id="next-escalation" readonly>
                           </div>
                       </div>
                   </div>
               </div>
           </div>
       </div>
       
       <!-- Bootstrap JS -->
       <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
       
       <script>
           // Variables globales
           let alertsData = {};
           let trendsChart = null;
           let destinationChart = null;
           let currentFilter = 'all';
           
           // Inicializar dashboard
           document.addEventListener('DOMContentLoaded', function() {
               loadAlertsData();
               loadAlertConfig();
               
               // Auto-refresh cada 30 segundos
               setInterval(loadAlertsData, 30000);
               
               // Event listeners para filtros
               document.querySelectorAll('.filter-tab').forEach(tab => {
                   tab.addEventListener('click', function() {
                       document.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
                       this.classList.add('active');
                       currentFilter = this.getAttribute('data-filter');
                       filterCriticalAlerts();
                   });
               });
           });
           
           // Cargar datos de alertas
           async function loadAlertsData() {
               try {
                   const response = await fetch('/api/alerts/dashboard-data');
                   alertsData = await response.json();
                   
                   updateStats();
                   updateExecutiveSummary();
                   updateCriticalAlerts();
                   updateRecommendations();
                   updateCharts();
                   
                   document.getElementById('last-update').textContent = 
                       'Última actualización: ' + new Date().toLocaleTimeString();
                   
                   // Ocultar loading
                   document.getElementById('loading-overlay').style.display = 'none';
                   
               } catch (error) {
                   console.error('Error cargando datos de alertas:', error);
                   showError('Error cargando datos de alertas');
               }
           }
           
           // Actualizar estadísticas principales
           function updateStats() {
               const summary = alertsData.summary || {};
               
               document.getElementById('critical-count').textContent = summary.critical_count || 0;
               document.getElementById('warning-count').textContent = summary.warning_count || 0;
               document.getElementById('attention-count').textContent = summary.attention_count || 0;
               document.getElementById('total-waiting').textContent = summary.total_waiting || 0;
           }
           
           // Actualizar resumen ejecutivo
           function updateExecutiveSummary() {
               const executive = alertsData.executive_summary || {};
               const container = document.getElementById('executive-summary');
               
               const trendIcon = getTrendIcon(executive.trend_direction);
               const trendColor = getTrendColor(executive.trend_direction);
               
               container.innerHTML = `
                   <div class="executive-item">
                       <div class="executive-number">${executive.total_camiones_problema || 0}</div>
                       <div class="executive-label">Camiones con Problemas</div>
                   </div>
                   <div class="executive-item">
                       <div class="executive-number">${executive.porcentaje_con_alertas || 0}%</div>
                       <div class="executive-label">% con Alertas</div>
                   </div>
                   <div class="executive-item">
                       <div class="executive-number">${executive.tiempo_espera_promedio || 0}h</div>
                       <div class="executive-label">Espera Promedio</div>
                   </div>
                   <div class="executive-item">
                       <div class="executive-number">${executive.alertas_nuevas_ultima_hora || 0}</div>
                       <div class="executive-label">Nuevas (1h)</div>
                   </div>
                   <div class="executive-item">
                       <div class="executive-number" style="color: ${trendColor};">
                           <i class="${trendIcon}"></i>
                       </div>
                       <div class="executive-label">Tendencia</div>
                   </div>
                   <div class="executive-item">
                       <div class="executive-number">${executive.next_escalation || 'N/A'}</div>
                       <div class="executive-label">Próx. Escalación</div>
                   </div>
               `;
           }
           
           // Obtener icono de tendencia
           function getTrendIcon(direction) {
               const icons = {
                   'increasing': 'fas fa-arrow-up',
                   'decreasing': 'fas fa-arrow-down',
                   'stable': 'fas fa-minus'
               };
               return icons[direction] || 'fas fa-minus';
           }
           
           // Obtener color de tendencia
           function getTrendColor(direction) {
               const colors = {
                   'increasing': '#dc3545',
                   'decreasing': '#28a745',
                   'stable': '#ffc107'
               };
               return colors[direction] || '#ffc107';
           }
           
           // Actualizar alertas críticas
           function updateCriticalAlerts() {
               const criticalAlerts = alertsData.critical_alerts_detailed || [];
               const container = document.getElementById('critical-alerts-list');
               
               if (criticalAlerts.length === 0) {
                   container.innerHTML = `
                       <div class="text-center text-success p-4">
                           <i class="fas fa-check-circle fa-3x mb-3"></i>
                           <h5>¡Excelente!</h5>
                           <p>No hay alertas críticas en este momento</p>
                       </div>
                   `;
                   return;
               }
               
               const alertsHtml = criticalAlerts.map(alert => {
                   const priorityClass = getPriorityClass(alert.prioridad);
                   const alertLevel = alert.alert_level || 'CRITICAL';
                   
                   const geocercasText = alert.geocercas_activas && alert.geocercas_activas.length > 0
                       ? alert.geocercas_activas.map(g => g.name).join(', ')
                       : 'Ninguna';
                   
                   return `
                       <div class="alert-item ${alertLevel.toLowerCase()}" onclick="centerOnTruckFromAlert('${alert.patente}')">
                           <div class="alert-header">
                               <div class="alert-title">
                                   <span class="priority-indicator ${priorityClass}"></span>
                                   ${alert.patente} - ${alert.deposito_destino}
                               </div>
                               <span class="alert-badge ${alertLevel.toLowerCase()}">${alertLevel}</span>
                           </div>
                           
                           <div class="alert-details">
                               <div class="alert-detail-item">
                                   <i class="fas fa-clock"></i>
                                   ${Math.floor(alert.tiempo_espera_horas)}h ${Math.round((alert.tiempo_espera_horas % 1) * 60)}m esperando
                               </div>
                               <div class="alert-detail-item">
                                   <i class="fas fa-file-alt"></i>
                                   Planilla: ${alert.planilla || 'N/A'}
                               </div>
                               <div class="alert-detail-item">
                                   <i class="fas fa-truck-loading"></i>
                                   ${alert.estado_entrega}
                               </div>
                               <div class="alert-detail-item">
                                   <i class="fas fa-map-marker-alt"></i>
                                   Geocercas: ${geocercasText}
                               </div>
                               <div class="alert-detail-item">
                                   <i class="fas fa-tachometer-alt"></i>
                                   Velocidad: ${alert.velocidad_kmh} km/h
                               </div>
                               <div class="alert-detail-item">
                                   <i class="fas fa-star"></i>
                                   Prioridad: ${alert.prioridad}/100
                               </div>
                           </div>
                           
                           ${alert.escalamiento_requerido ? `
                           <div class="mt-2">
                               <span class="badge bg-danger">
                                   <i class="fas fa-exclamation-triangle"></i> Requiere escalación inmediata
                               </span>
                           </div>
                           ` : ''}
                       </div>
                   `;
               }).join('');
               
               container.innerHTML = alertsHtml;
           }
           
           // Obtener clase de prioridad
           function getPriorityClass(priority) {
               if (priority >= 80) return 'priority-high';
               if (priority >= 50) return 'priority-medium';
               return 'priority-low';
           }
           
           // Filtrar alertas críticas
           function filterCriticalAlerts() {
               const allAlerts = document.querySelectorAll('.alert-item');
               
               allAlerts.forEach(alert => {
                   let show = true;
                   
                   switch (currentFilter) {
                       case 'critical':
                           show = alert.classList.contains('critical');
                           break;
                       case 'high-priority':
                           show = alert.querySelector('.priority-high') !== null;
                           break;
                       case 'docks':
                           show = alert.textContent.includes('DOCKS');
                           break;
                       case 'all':
                       default:
                           show = true;
                           break;
                   }
                   
                   alert.style.display = show ? 'block' : 'none';
               });
           }
           
           // Actualizar recomendaciones
           function updateRecommendations() {
               const recommendations = alertsData.recommendations || [];
               const container = document.getElementById('recommendations-list');
               
               if (recommendations.length === 0) {
                   container.innerHTML = `
                       <li class="recommendation-item">
                           <i class="fas fa-check-circle text-success"></i>
                           <strong>Sistema funcionando correctamente</strong><br>
                           No hay recomendaciones críticas en este momento.
                       </li>
                   `;
                   return;
               }
               
               const recommendationsHtml = recommendations.map(rec => `
                   <li class="recommendation-item ${rec.type}">
                       <div class="d-flex align-items-start">
                           <div class="me-3">
                               <i class="fas ${getRecommendationIcon(rec.type)} fa-lg"></i>
                           </div>
                           <div class="flex-grow-1">
                               <strong>${rec.title}</strong><br>
                               <small class="text-muted">${rec.description}</small><br>
                               <em>Acción: ${rec.action}</em>
                               <span class="badge bg-secondary float-end">${rec.priority}</span>
                           </div>
                       </div>
                   </li>
               `).join('');
               
               container.innerHTML = recommendationsHtml;
           }
           
           // Obtener icono de recomendación
           function getRecommendationIcon(type) {
               const icons = {
                   'urgent': 'fa-fire',
                   'attention': 'fa-exclamation-triangle',
                   'operational': 'fa-cogs'
               };
               return icons[type] || 'fa-lightbulb';
           }
           
           // Actualizar gráficos
           function updateCharts() {
               updateTrendsChart();
               updateDestinationChart();
           }
           
           // Actualizar gráfico de tendencias
           function updateTrendsChart() {
               const ctx = document.getElementById('trendsChart').getContext('2d');
               const trends = alertsData.hourly_trends || [];
               
               if (trendsChart) {
                   trendsChart.destroy();
               }
               
               trendsChart = new Chart(ctx, {
                   type: 'line',
                   data: {
                       labels: trends.map(t => t.hour),
                       datasets: [
                           {
                               label: 'Críticas',
                               data: trends.map(t => t.critical),
                               borderColor: '#dc3545',
                               backgroundColor: 'rgba(220, 53, 69, 0.1)',
                               tension: 0.4,
                               fill: true
                           },
                           {
                               label: 'Advertencias',
                               data: trends.map(t => t.warning),
                               borderColor: '#ffc107',
                               backgroundColor: 'rgba(255, 193, 7, 0.1)',
                               tension: 0.4,
                               fill: true
                           },
                           {
                               label: 'Atención',
                               data: trends.map(t => t.attention),
                               borderColor: '#17a2b8',
                               backgroundColor: 'rgba(23, 162, 184, 0.1)',
                               tension: 0.4,
                               fill: true
                           }
                       ]
                   },
                   options: {
                       responsive: true,
                       maintainAspectRatio: false,
                       plugins: {
                           title: {
                               display: true,
                               text: 'Evolución de Alertas por Hora'
                           },
                           legend: {
                               position: 'top'
                           }
                       },
                       scales: {
                           y: {
                               beginAtZero: true,
                               title: {
                                   display: true,
                                   text: 'Número de Alertas'
                               }
                           },
                           x: {
                               title: {
                                   display: true,
                                   text: 'Hora'
                               }
                           }
                       }
                   }
               });
           }
           
           // Actualizar gráfico de destinos
           function updateDestinationChart() {
               const ctx = document.getElementById('destinationChart').getContext('2d');
               const destinations = alertsData.alerts_by_destination || {};
               
               if (destinationChart) {
                   destinationChart.destroy();
               }
               
               const labels = Object.keys(destinations);
               const data = labels.map(dest => destinations[dest].total);
               
               destinationChart = new Chart(ctx, {
                   type: 'doughnut',
                   data: {
                       labels: labels,
                       datasets: [{
                           data: data,
                           backgroundColor: [
                               '#dc3545',
                               '#ffc107',
                               '#17a2b8',
                               '#28a745',
                               '#6f42c1',
                               '#fd7e14'
                           ],
                           borderWidth: 2,
                           borderColor: '#fff'
                       }]
                   },
                   options: {
                       responsive: true,
                       maintainAspectRatio: false,
                       plugins: {
                           title: {
                               display: true,
                               text: 'Distribución por Destino'
                           },
                           legend: {
                               position: 'bottom'
                           }
                       }
                   }
               });
           }
           
           // Centrar en camión desde alerta
           function centerOnTruckFromAlert(patente) {
               // Abrir mapa en nueva pestaña centrado en el camión
               window.open(`/map-dashboard#truck=${patente}`, '_blank');
           }
           
           // Cargar configuración de alertas
           async function loadAlertConfig() {
               try {
                   const response = await fetch('/api/alerts/configuration');
                   const config = await response.json();
                   
                   document.getElementById('normal-hours').value = config.thresholds.normal_hours;
                   document.getElementById('warning-hours').value = config.thresholds.warning_hours;
                   document.getElementById('critical-hours').value = config.thresholds.critical_hours;
                   document.getElementById('next-escalation').value = alertsData.next_escalation || '2 horas';
                   
                   document.getElementById('email-notifications').checked = config.notification_settings.email_enabled;
                   document.getElementById('auto-escalation').checked = config.notification_settings.auto_escalation;
                   
               } catch (error) {
                   console.error('Error cargando configuración:', error);
               }
           }
           
           // Actualizar configuración de alertas
           async function updateAlertConfig() {
               try {
                   const config = {
                       thresholds: {
                           normal_hours: parseFloat(document.getElementById('normal-hours').value),
                           warning_hours: parseFloat(document.getElementById('warning-hours').value),
                           critical_hours: parseFloat(document.getElementById('critical-hours').value)
                       },
                       notification_settings: {
                           email_enabled: document.getElementById('email-notifications').checked,
                           auto_escalation: document.getElementById('auto-escalation').checked
                       }
                   };
                   
                   const response = await fetch('/api/alerts/configuration', {
                       method: 'POST',
                       headers: {
                           'Content-Type': 'application/json'
                       },
                       body: JSON.stringify(config)
                   });
                   
                   if (response.ok) {
                       showSuccess('Configuración actualizada correctamente');
                       setTimeout(loadAlertsData, 1000); // Recargar datos
                   } else {
                       showError('Error actualizando configuración');
                   }
                   
               } catch (error) {
                   console.error('Error actualizando configuración:', error);
                   showError('Error actualizando configuración');
               }
           }
           
           // Restaurar configuración por defecto
           function resetAlertConfig() {
               document.getElementById('normal-hours').value = 4;
               document.getElementById('warning-hours').value = 8;
               document.getElementById('critical-hours').value = 48;
               document.getElementById('email-notifications').checked = true;
               document.getElementById('auto-escalation').checked = true;
           }
           
           // Refrescar alertas manualmente
           function refreshAlerts() {
               document.getElementById('refresh-status').innerHTML = 
                   '<span class="spinner-border spinner-border-sm me-1"></span>Actualizando...';
               
               loadAlertsData().then(() => {
                   document.getElementById('refresh-status').innerHTML = 
                       '<span class="refresh-dot"></span>Actualizado correctamente';
                       
                   setTimeout(() => {
                       document.getElementById('refresh-status').textContent = 'Actualizando cada 30s';
                   }, 2000);
               });
           }
           
           // Mostrar mensaje de éxito
           function showSuccess(message) {
               // Crear toast de éxito
               const toast = document.createElement('div');
               toast.className = 'toast-message success';
               toast.innerHTML = `<i class="fas fa-check-circle"></i> ${message}`;
               document.body.appendChild(toast);
               
               setTimeout(() => {
                   toast.remove();
               }, 3000);
           }
           
           // Mostrar mensaje de error
           function showError(message) {
               // Crear toast de error
               const toast = document.createElement('div');
               toast.className = 'toast-message error';
               toast.innerHTML = `<i class="fas fa-exclamation-circle"></i> ${message}`;
               document.body.appendChild(toast);
               
               setTimeout(() => {
                   toast.remove();
               }, 5000);
           }
       </script>
       
       <style>
           .toast-message {
               position: fixed;
               top: 80px;
               right: 20px;
               padding: 15px 20px;
               border-radius: 8px;
               color: white;
               font-weight: bold;
               z-index: 10000;
               animation: slideIn 0.3s ease;
           }
           
           .toast-message.success {
               background: #28a745;
           }
           
           .toast-message.error {
               background: #dc3545;
           }
           
           @keyframes slideIn {
               from { transform: translateX(100%); opacity: 0; }
               to { transform: translateX(0); opacity: 1; }
           }
       </style>
   </body>
   </html>
   '''

# Nuevos endpoints de la API de alertas
@alerts_ns.route('/dashboard-data')
class AlertsDashboardData(Resource):
   @alerts_ns.doc('get_alerts_dashboard_data')
   def get(self):
       """Obtiene datos completos para el dashboard de alertas"""
       try:
           if not tracking_service_complete:
               init_complete_service()

           data = tracking_service_complete.get_alerts_dashboard_data()
           return data, 200

       except Exception as e:
           api.abort(500, f"Error obteniendo datos dashboard: {str(e)}")


@alerts_ns.route('/configuration')
class AlertsConfiguration(Resource):
    @alerts_ns.doc('get_alerts_configuration')
    def get(self):
        """Obtiene configuración actual de alertas"""
        try:
            if not tracking_service_complete:
                init_complete_service()

            config = tracking_service_complete.get_alert_configurations()
            return config, 200

        except Exception as e:
            api.abort(500, f"Error obteniendo configuración: {str(e)}")

    @alerts_ns.doc('update_alerts_configuration')
    def post(self):
        """Actualiza configuración de alertas"""
        try:
            if not tracking_service_complete:
                init_complete_service()

            new_config = request.get_json()
            success = tracking_service_complete.update_alert_configurations(new_config)

            if success:
                return {'message': 'Configuración actualizada correctamente'}, 200
            else:
                api.abort(400, "Error actualizando configuración")

        except Exception as e:
            api.abort(500, f"Error actualizando configuración: {str(e)}")


@alerts_ns.route('/report')
class AlertsReport(Resource):
    @alerts_ns.doc('generate_alerts_report')
    def get(self):
        """Genera reporte de alertas para un período"""
        try:
            if not tracking_service_complete:
                init_complete_service()

            # Obtener parámetros de fecha
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')

            if start_date:
                start_date = datetime.strptime(start_date, '%Y-%m-%d')
            if end_date:
                end_date = datetime.strptime(end_date, '%Y-%m-%d')

            report = tracking_service_complete.generate_alert_report(start_date, end_date)
            return report, 200

        except Exception as e:
            api.abort(500, f"Error generando reporte: {str(e)}")


@alerts_ns.route('/notification')
class AlertsNotification(Resource):
    @alerts_ns.doc('create_alert_notification')
    def post(self):
        """Crea notificación de alerta"""
        try:
            if not tracking_service_complete:
                init_complete_service()

            alert_data = request.get_json()
            notification_type = request.args.get('type', 'email')

            notification = tracking_service_complete.create_alert_notification(alert_data, notification_type)

            if notification:
                return notification, 201
            else:
                api.abort(400, "Error creando notificación")

        except Exception as e:
            api.abort(500, f"Error creando notificación: {str(e)}")

# ===============================
# NUEVOS ENDPOINTS PARA MAPA INTERACTIVO
# ===============================

@app.route('/map-dashboard')
def map_dashboard():
    """Dashboard avanzado con mapa interactivo de Leaflet"""
    return '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Mapa Tracking CBN - Dashboard Interactivo</title>

        <!-- Leaflet CSS -->
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />

        <!-- Bootstrap 5 -->
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">

        <!-- Font Awesome -->
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">

        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                background: #f8f9fa;
                margin: 0;
                padding: 0;
            }

            .header-bar {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 15px 0;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }

            .header-bar h1 {
                margin: 0;
                font-size: 1.8rem;
                font-weight: bold;
            }

            .stats-row {
                background: white;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                margin: 20px 0;
                padding: 20px;
            }

            .stat-card {
                text-align: center;
                padding: 15px;
                border-radius: 8px;
                background: linear-gradient(135deg, #f8f9fa, #e9ecef);
                margin: 5px;
                transition: transform 0.2s ease;
            }

            .stat-card:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            }

            .stat-number {
                font-size: 2rem;
                font-weight: bold;
                color: #667eea;
                margin: 0;
            }

            .stat-label {
                color: #666;
                font-size: 0.9rem;
                margin: 5px 0 0 0;
            }

            .stat-card.critical .stat-number { color: #dc3545; }
            .stat-card.warning .stat-number { color: #ffc107; }
            .stat-card.success .stat-number { color: #28a745; }
            .stat-card.info .stat-number { color: #17a2b8; }

            #map {
                height: 500px;
                border-radius: 10px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                border: 2px solid #e9ecef;
            }

            .controls-panel {
                background: white;
                border-radius: 10px;
                padding: 20px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                margin-bottom: 20px;
            }

            .filter-group {
                margin-bottom: 15px;
            }

            .filter-group label {
                font-weight: bold;
                color: #495057;
                margin-bottom: 5px;
                display: block;
            }

            .btn-filter {
                margin: 2px;
                border-radius: 20px;
                padding: 5px 15px;
                font-size: 0.85rem;
                transition: all 0.2s ease;
            }

            .btn-filter.active {
                transform: scale(1.05);
                box-shadow: 0 2px 8px rgba(0,0,0,0.2);
            }

            .truck-list {
                background: white;
                border-radius: 10px;
                padding: 20px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                max-height: 400px;
                overflow-y: auto;
            }

            .truck-item {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 10px 15px;
                margin: 5px 0;
                border-radius: 8px;
                background: #f8f9fa;
                border-left: 4px solid #667eea;
                transition: all 0.2s ease;
            }

            .truck-item:hover {
                background: #e9ecef;
                transform: translateX(5px);
            }

            .truck-item.critical { border-left-color: #dc3545; }
            .truck-item.warning { border-left-color: #ffc107; }
            .truck-item.attention { border-left-color: #17a2b8; }
            .truck-item.normal { border-left-color: #28a745; }

            .truck-info h6 {
                margin: 0;
                font-weight: bold;
                color: #333;
            }

            .truck-info small {
                color: #666;
            }

            .truck-status {
                text-align: right;
            }

            .status-badge {
                padding: 4px 10px;
                border-radius: 15px;
                font-size: 0.75rem;
                font-weight: bold;
                text-transform: uppercase;
            }

            .status-badge.critical { background: #dc3545; color: white; }
            .status-badge.warning { background: #ffc107; color: #212529; }
            .status-badge.attention { background: #17a2b8; color: white; }
            .status-badge.normal { background: #28a745; color: white; }

            .loading {
                text-align: center;
                padding: 40px;
                color: #666;
            }

            .spinner-border {
                width: 3rem;
                height: 3rem;
            }

            .legend {
                background: white;
                padding: 15px;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                margin-top: 15px;
            }

            .legend-item {
                display: flex;
                align-items: center;
                margin: 5px 0;
            }

            .legend-color {
                width: 20px;
                height: 20px;
                border-radius: 50%;
                margin-right: 10px;
                border: 2px solid #fff;
                box-shadow: 0 1px 3px rgba(0,0,0,0.3);
            }

            .auto-refresh {
                position: fixed;
                top: 20px;
                right: 20px;
                background: rgba(255,255,255,0.95);
                padding: 10px 15px;
                border-radius: 25px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                font-size: 0.85rem;
                color: #666;
                z-index: 1000;
            }

            .refresh-indicator {
                display: inline-block;
                width: 8px;
                height: 8px;
                background: #28a745;
                border-radius: 50%;
                margin-right: 8px;
                animation: pulse 2s infinite;
            }

            @keyframes pulse {
                0% { opacity: 1; }
                50% { opacity: 0.5; }
                100% { opacity: 1; }
            }

            .fullscreen-toggle {
                position: absolute;
                top: 10px;
                right: 10px;
                background: white;
                border: none;
                border-radius: 5px;
                padding: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                cursor: pointer;
                z-index: 1000;
            }
        </style>
    </head>
    <body>
        <!-- Auto-refresh indicator -->
        <div class="auto-refresh">
            <span class="refresh-indicator"></span>
            <span id="refresh-status">Actualizando cada 30s</span>
        </div>

        <!-- Header -->
        <div class="header-bar">
            <div class="container-fluid">
                <div class="row align-items-center">
                    <div class="col-md-6">
                        <h1><i class="fas fa-map-marked-alt"></i> Mapa Tracking CBN</h1>
                    </div>
                    <div class="col-md-6 text-end">
                        <span id="last-update" class="badge bg-light text-dark">Cargando...</span>
                        <button class="btn btn-light btn-sm ms-2" onclick="refreshData()">
                            <i class="fas fa-sync-alt"></i> Actualizar
                        </button>
                        <a href="/dashboard" class="btn btn-outline-light btn-sm ms-2">
                            <i class="fas fa-chart-bar"></i> Dashboard Clásico
                        </a>
                    </div>
                </div>
            </div>
        </div>

        <div class="container-fluid">
            <!-- Stats Row -->
            <div class="stats-row">
                <div class="row" id="stats-container">
                    <div class="col-md-2">
                        <div class="stat-card">
                            <div id="total-trucks" class="stat-number">-</div>
                            <div class="stat-label">Total Camiones</div>
                        </div>
                    </div>
                    <div class="col-md-2">
                        <div class="stat-card critical">
                            <div id="critical-alerts" class="stat-number">-</div>
                            <div class="stat-label">Críticas</div>
                        </div>
                    </div>
                    <div class="col-md-2">
                        <div class="stat-card warning">
                            <div id="warning-alerts" class="stat-number">-</div>
                            <div class="stat-label">Advertencias</div>
                        </div>
                    </div>
                    <div class="col-md-2">
                        <div class="stat-card info">
                            <div id="attention-alerts" class="stat-number">-</div>
                            <div class="stat-label">Atención</div>
                        </div>
                    </div>
                    <div class="col-md-2">
                        <div class="stat-card success">
                            <div id="avg-progress" class="stat-number">-</div>
                            <div class="stat-label">Progreso Promedio</div>
                        </div>
                    </div>
                    <div class="col-md-2">
                        <div class="stat-card info">
                            <div id="in-geocercas" class="stat-number">-</div>
                            <div class="stat-label">En Geocercas</div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="row">
                <!-- Controls Panel -->
                <div class="col-md-3">
                    <div class="controls-panel">
                        <h5><i class="fas fa-filter"></i> Filtros</h5>

                        <div class="filter-group">
                            <label>Por Estado de Alerta:</label>
                            <div>
                                <button class="btn btn-outline-secondary btn-filter btn-sm active" data-filter="all-alerts">
                                    <i class="fas fa-globe"></i> Todos
                                </button>
                                <button class="btn btn-outline-danger btn-filter btn-sm" data-filter="critical">
                                    <i class="fas fa-exclamation-triangle"></i> Críticas
                                </button>
                                <button class="btn btn-outline-warning btn-filter btn-sm" data-filter="warning">
                                    <i class="fas fa-exclamation"></i> Advertencias
                                </button>
                                <button class="btn btn-outline-info btn-filter btn-sm" data-filter="attention">
                                    <i class="fas fa-info"></i> Atención
                                </button>
                                <button class="btn btn-outline-success btn-filter btn-sm" data-filter="normal">
                                    <i class="fas fa-check"></i> Normales
                                </button>
                            </div>
                        </div>

                        <div class="filter-group">
                            <label>Por Geocerca:</label>
                            <div>
                                <button class="btn btn-outline-secondary btn-filter btn-sm active" data-filter="all-geo">
                                    <i class="fas fa-map"></i> Todas
                                </button>
                                <button class="btn btn-outline-primary btn-filter btn-sm" data-filter="docks">
                                    <i class="fas fa-warehouse"></i> DOCKS
                                </button>
                                <button class="btn btn-outline-primary btn-filter btn-sm" data-filter="track-trace">
                                    <i class="fas fa-route"></i> Track&Trace
                                </button>
                                <button class="btn btn-outline-primary btn-filter btn-sm" data-filter="cbn">
                                    <i class="fas fa-building"></i> CBN
                                </button>
                                <button class="btn btn-outline-primary btn-filter btn-sm" data-filter="ciudades">
                                    <i class="fas fa-city"></i> Ciudades
                                </button>
                            </div>
                        </div>

                        <div class="filter-group">
                            <label>Por Estado de Entrega:</label>
                            <div>
                                <button class="btn btn-outline-secondary btn-filter btn-sm active" data-filter="all-delivery">
                                    <i class="fas fa-truck"></i> Todos
                                </button>
                                <button class="btn btn-outline-info btn-filter btn-sm" data-filter="en-transito">
                                    <i class="fas fa-road"></i> En Tránsito
                                </button>
                                <button class="btn btn-outline-warning btn-filter btn-sm" data-filter="en-ciudad">
                                    <i class="fas fa-map-marker"></i> En Ciudad
                                </button>
                                <button class="btn btn-outline-success btn-filter btn-sm" data-filter="descargando">
                                    <i class="fas fa-download"></i> Descargando
                                </button>
                            </div>
                        </div>

                        <div class="d-grid gap-2 mt-3">
                            <button class="btn btn-outline-primary" onclick="centerMapBolivia()">
                                <i class="fas fa-crosshairs"></i> Centrar Bolivia
                            </button>
                            <button class="btn btn-outline-secondary" onclick="clearFilters()">
                                <i class="fas fa-eraser"></i> Limpiar Filtros
                            </button>
                        </div>
                    </div>

                    <!-- Legend -->
                    <div class="legend">
                        <h6><i class="fas fa-info-circle"></i> Leyenda</h6>
                        <div class="legend-item">
                            <div class="legend-color" style="background: #dc3545;"></div>
                            <span>Crítico (>48h esperando)</span>
                        </div>
                        <div class="legend-item">
                            <div class="legend-color" style="background: #ffc107;"></div>
                            <span>Advertencia (>8h esperando)</span>
                        </div>
                        <div class="legend-item">
                            <div class="legend-color" style="background: #17a2b8;"></div>
                            <span>Atención (>4h esperando)</span>
                        </div>
                        <div class="legend-item">
                            <div class="legend-color" style="background: #28a745;"></div>
                            <span>Normal (sin espera)</span>
                        </div>
                    </div>
                </div>

                <!-- Map Container -->
                <div class="col-md-6">
                    <div class="position-relative">
                        <div id="map"></div>
                        <button class="fullscreen-toggle" onclick="toggleFullscreen()" title="Pantalla completa">
                            <i class="fas fa-expand"></i>
                        </button>
                    </div>
                </div>

                <!-- Truck List -->
                <div class="col-md-3">
                    <div class="truck-list">
                        <h5><i class="fas fa-truck"></i> Camiones Activos</h5>
                        <div id="truck-list-content">
                            <div class="loading">
                                <div class="spinner-border text-primary" role="status">
                                    <span class="visually-hidden">Cargando...</span>
                                </div>
                                <p class="mt-2">Cargando camiones...</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Leaflet JS -->
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

        <!-- Bootstrap JS -->
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>

        <script>
            // Variables globales
            let map;
            let markersLayer;
            let trucksData = [];
            let filteredTrucks = [];
            let activeFilters = {
                alert: 'all-alerts',
                geocerca: 'all-geo',
                delivery: 'all-delivery'
            };

            // Inicializar mapa
            function initMap() {
                map = L.map('map').setView([-16.2902, -63.5887], 6); // Centro de Bolivia

                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                    attribution: '© OpenStreetMap contributors | CBN Tracking System',
                    maxZoom: 18
                }).addTo(map);

                markersLayer = L.layerGroup().addTo(map);
            }

            // Cargar datos de camiones
            async function loadTrucksData() {
                try {
                    const response = await fetch('/api/tracking/status-complete');
                    const data = await response.json();

                    trucksData = data || [];
                    updateStats();
                    applyFilters();
                    updateTruckList();

                    document.getElementById('last-update').textContent = 
                        'Última actualización: ' + new Date().toLocaleTimeString();

                } catch (error) {
                    console.error('Error cargando datos:', error);
                    showError('Error cargando datos de camiones');
                }
            }

            // Actualizar estadísticas
            function updateStats() {
                const totalTrucks = trucksData.length;
                const criticalCount = trucksData.filter(t => t.alert_level === 'CRITICAL').length;
                const warningCount = trucksData.filter(t => t.alert_level === 'WARNING').length;
                const attentionCount = trucksData.filter(t => t.alert_level === 'ATTENTION').length;
                const avgProgress = totalTrucks > 0 ? 
                    (trucksData.reduce((sum, t) => sum + (t.porcentaje_entrega || 0), 0) / totalTrucks).toFixed(1) : 0;
                const inGeocercas = trucksData.filter(t => 
                    t.en_docks !== 'NO' || t.en_track_trace !== 'NO' || t.en_cbn !== 'NO' || t.en_ciudades !== 'NO'
                ).length;

                document.getElementById('total-trucks').textContent = totalTrucks;
                document.getElementById('critical-alerts').textContent = criticalCount;
                document.getElementById('warning-alerts').textContent = warningCount;
                document.getElementById('attention-alerts').textContent = attentionCount;
                document.getElementById('avg-progress').textContent = avgProgress + '%';
                document.getElementById('in-geocercas').textContent = inGeocercas;
            }

            // Aplicar filtros
            function applyFilters() {
                filteredTrucks = trucksData.filter(truck => {
                    // Filtro por alerta
                    if (activeFilters.alert !== 'all-alerts') {
                        if (truck.alert_level.toLowerCase() !== activeFilters.alert) {
                            return false;
                        }
                    }

                    // Filtro por geocerca
                    if (activeFilters.geocerca !== 'all-geo') {
                        let inGeocerca = false;
                        switch (activeFilters.geocerca) {
                            case 'docks':
                                inGeocerca = truck.en_docks !== 'NO';
                                break;
                            case 'track-trace':
                                inGeocerca = truck.en_track_trace !== 'NO';
                                break;
                            case 'cbn':
                                inGeocerca = truck.en_cbn !== 'NO';
                                break;
                            case 'ciudades':
                                inGeocerca = truck.en_ciudades !== 'NO';
                                break;
                        }
                        if (!inGeocerca) return false;
                    }

                    // Filtro por estado de entrega
                    if (activeFilters.delivery !== 'all-delivery') {
                        switch (activeFilters.delivery) {
                            case 'en-transito':
                                if (truck.estado_entrega !== 'EN_TRANSITO') return false;
                                break;
                            case 'en-ciudad':
                                if (!truck.estado_entrega.includes('CIUDAD')) return false;
                                break;
                            case 'descargando':
                                if (!truck.estado_entrega.includes('DESCARGA')) return false;
                                break;
                        }
                    }

                    return true;
                });

                updateMapMarkers();
            }

            // Actualizar marcadores en el mapa
            function updateMapMarkers() {
                markersLayer.clearLayers();

                filteredTrucks.forEach(truck => {
                    if (truck.latitude && truck.longitude) {
                        const marker = createTruckMarker(truck);
                        markersLayer.addLayer(marker);
                    }
                });
            }

            // Crear marcador para camión
            function createTruckMarker(truck) {
                const alertColor = getAlertColor(truck.alert_level);
                const iconHtml = `
                    <div style="
                        background: ${alertColor};
                        border: 3px solid white;
                        border-radius: 50%;
                        width: 30px;
                        height: 30px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                        font-size: 14px;
                        color: white;
                        font-weight: bold;
                    ">
                        🚛
                    </div>
                `;

                const customIcon = L.divIcon({
                    html: iconHtml,
                    iconSize: [30, 30],
                    iconAnchor: [15, 15],
                    popupAnchor: [0, -15],
                    className: 'custom-truck-marker'
                });

                const marker = L.marker([truck.latitude, truck.longitude], { icon: customIcon });

                // Popup con información detallada
                const popupContent = createPopupContent(truck);
                marker.bindPopup(popupContent, { maxWidth: 350 });

                // Event listener para centrar en camión desde la lista
                marker.truckData = truck;

                return marker;
            }

            // Obtener color según nivel de alerta
            function getAlertColor(alertLevel) {
                const colors = {
                    'CRITICAL': '#dc3545',
                    'WARNING': '#ffc107', 
                    'ATTENTION': '#17a2b8',
                    'NORMAL': '#28a745'
                };
                return colors[alertLevel] || colors['NORMAL'];
            }

            // Crear contenido del popup
            function createPopupContent(truck) {
                const alertEmoji = {
                    'CRITICAL': '🚨',
                    'WARNING': '⚠️',
                    'ATTENTION': '🔔',
                    'NORMAL': '✅'
                };

                const geocercasActivas = [];
                if (truck.en_docks !== 'NO') geocercasActivas.push(`DOCKS: ${truck.en_docks}`);
                if (truck.en_track_trace !== 'NO') geocercasActivas.push(`T&T: ${truck.en_track_trace}`);
                if (truck.en_cbn !== 'NO') geocercasActivas.push(`CBN: ${truck.en_cbn}`);
                if (truck.en_ciudades !== 'NO') geocercasActivas.push(`Ciudad: ${truck.en_ciudades}`);

                const tiempoEspera = truck.tiempo_espera_horas > 0 ? 
                    `${Math.floor(truck.tiempo_espera_horas)}h ${Math.round((truck.tiempo_espera_horas % 1) * 60)}m` : 
                    'Sin espera';

                return `
                    <div style="font-family: Arial, sans-serif;">
                        <h6 style="margin: 0 0 10px 0; color: #333; border-bottom: 2px solid ${getAlertColor(truck.alert_level)}; padding-bottom: 5px;">
                            <strong>${truck.patente}</strong>
                            <span style="float: right;">${alertEmoji[truck.alert_level] || '📍'}</span>
                        </h6>

                        <div style="margin-bottom: 8px;">
                            <strong>📋 Planilla:</strong> ${truck.planilla || 'N/A'}
                        </div>

                        <div style="margin-bottom: 8px;">
                            <strong>📍 Destino:</strong> ${truck.deposito_destino || 'N/A'}
                        </div>

                        <div style="margin-bottom: 8px;">
                            <strong>📊 Progreso:</strong> 
                            <div style="background: #f0f0f0; border-radius: 10px; overflow: hidden; margin-top: 3px;">
                                <div style="background: ${getAlertColor(truck.alert_level)}; height: 8px; width: ${truck.porcentaje_entrega || 0}%; transition: width 0.3s ease;"></div>
                            </div>
                            <small>${truck.porcentaje_entrega || 0}% completado</small>
                        </div>

                        <div style="margin-bottom: 8px;">
                            <strong>🚛 Estado:</strong> ${truck.estado_entrega || 'EN_TRANSITO'}
                        </div>

                        <div style="margin-bottom: 8px;">
                            <strong>⏰ Tiempo espera:</strong> ${tiempoEspera}
                        </div>

                        ${truck.velocidad_kmh ? `
                        <div style="margin-bottom: 8px;">
                            <strong>🏃 Velocidad:</strong> ${truck.velocidad_kmh} km/h
                        </div>
                        ` : ''}

                        ${geocercasActivas.length > 0 ? `
                        <div style="margin-bottom: 8px;">
                            <strong>🗺️ En geocercas:</strong><br>
                            <small style="color: #666;">${geocercasActivas.join('<br>')}</small>
                        </div>
                        ` : ''}

                        <div style="text-align: center; margin-top: 10px; padding-top: 10px; border-top: 1px solid #eee;">
                            <button onclick="centerOnTruck('${truck.patente}')" style="background: #667eea; color: white; border: none; padding: 5px 10px; border-radius: 15px; font-size: 0.8rem; cursor: pointer;">
                                📍 Centrar en mapa
                            </button>
                        </div>
                    </div>
                `;
            }

            // Actualizar lista de camiones
            function updateTruckList() {
                const container = document.getElementById('truck-list-content');

                if (filteredTrucks.length === 0) {
                    container.innerHTML = `
                        <div class="text-center text-muted">
                            <i class="fas fa-search fa-2x mb-2"></i>
                            <p>No hay camiones que coincidan con los filtros seleccionados</p>
                       </div>
                   `;
                   return;
               }
               
               const sortedTrucks = filteredTrucks.sort((a, b) => {
                   const alertOrder = {'CRITICAL': 0, 'WARNING': 1, 'ATTENTION': 2, 'NORMAL': 3};
                   const aOrder = alertOrder[a.alert_level] || 4;
                   const bOrder = alertOrder[b.alert_level] || 4;
                   
                   if (aOrder !== bOrder) return aOrder - bOrder;
                   return (b.tiempo_espera_horas || 0) - (a.tiempo_espera_horas || 0);
               });
               
               const html = sortedTrucks.map(truck => {
                   const alertClass = truck.alert_level.toLowerCase();
                   const tiempoEspera = truck.tiempo_espera_horas > 0 ? 
                       `${Math.floor(truck.tiempo_espera_horas)}h ${Math.round((truck.tiempo_espera_horas % 1) * 60)}m` : 
                       'Sin espera';
                       
                   return `
                       <div class="truck-item ${alertClass}" onclick="centerOnTruckFromList('${truck.patente}')" style="cursor: pointer;">
                           <div class="truck-info">
                               <h6>${truck.patente}</h6>
                               <small>${truck.deposito_destino || 'Sin destino'}</small><br>
                               <small class="text-muted">${truck.estado_entrega || 'EN_TRANSITO'}</small>
                           </div>
                           <div class="truck-status">
                               <span class="status-badge ${alertClass}">${truck.alert_level}</span>
                               <br><small class="text-muted">${tiempoEspera}</small>
                               <br><small class="text-primary">${truck.porcentaje_entrega || 0}%</small>
                           </div>
                       </div>
                   `;
               }).join('');
               
               container.innerHTML = html;
           }
           
           // Centrar mapa en camión específico
           function centerOnTruck(patente) {
               const truck = trucksData.find(t => t.patente === patente);
               if (truck && truck.latitude && truck.longitude) {
                   map.setView([truck.latitude, truck.longitude], 14);
                   
                   // Encontrar y abrir popup del marcador
                   markersLayer.eachLayer(layer => {
                       if (layer.truckData && layer.truckData.patente === patente) {
                           layer.openPopup();
                       }
                   });
               }
           }
           
           // Centrar en camión desde la lista
           function centerOnTruckFromList(patente) {
               centerOnTruck(patente);
           }
           
           // Centrar mapa en Bolivia
           function centerMapBolivia() {
               map.setView([-16.2902, -63.5887], 6);
           }
           
           // Limpiar todos los filtros
           function clearFilters() {
               activeFilters = {
                   alert: 'all-alerts',
                   geocerca: 'all-geo', 
                   delivery: 'all-delivery'
               };
               
               // Actualizar botones activos
               document.querySelectorAll('.btn-filter').forEach(btn => {
                   btn.classList.remove('active');
               });
               
               document.querySelectorAll('[data-filter="all-alerts"], [data-filter="all-geo"], [data-filter="all-delivery"]').forEach(btn => {
                   btn.classList.add('active');
               });
               
               applyFilters();
               updateTruckList();
           }
           
           // Alternar pantalla completa del mapa
           function toggleFullscreen() {
               const mapContainer = document.getElementById('map');
               const button = document.querySelector('.fullscreen-toggle i');
               
               if (mapContainer.style.position === 'fixed') {
                   // Salir de pantalla completa
                   mapContainer.style.position = '';
                   mapContainer.style.top = '';
                   mapContainer.style.left = '';
                   mapContainer.style.width = '';
                   mapContainer.style.height = '';
                   mapContainer.style.zIndex = '';
                   mapContainer.style.background = '';
                   
                   button.className = 'fas fa-expand';
               } else {
                   // Entrar en pantalla completa
                   mapContainer.style.position = 'fixed';
                   mapContainer.style.top = '0';
                   mapContainer.style.left = '0';
                   mapContainer.style.width = '100vw';
                   mapContainer.style.height = '100vh';
                   mapContainer.style.zIndex = '9999';
                   mapContainer.style.background = 'white';
                   
                   button.className = 'fas fa-compress';
               }
               
               setTimeout(() => {
                   map.invalidateSize();
               }, 100);
           }
           
           // Refrescar datos manualmente
           function refreshData() {
               document.getElementById('refresh-status').innerHTML = 
                   '<span class="spinner-border spinner-border-sm me-1"></span>Actualizando...';
               
               loadTrucksData().then(() => {
                   document.getElementById('refresh-status').innerHTML = 
                       '<span class="refresh-indicator"></span>Actualizado correctamente';
                       
                   setTimeout(() => {
                       document.getElementById('refresh-status').textContent = 'Actualizando cada 30s';
                   }, 2000);
               });
           }
           
           // Mostrar error
           function showError(message) {
               const container = document.getElementById('truck-list-content');
               container.innerHTML = `
                   <div class="text-center text-danger">
                       <i class="fas fa-exclamation-triangle fa-2x mb-2"></i>
                       <p>${message}</p>
                       <button class="btn btn-outline-primary btn-sm" onclick="refreshData()">
                           <i class="fas fa-retry"></i> Reintentar
                       </button>
                   </div>
               `;
           }
           
           // Event listeners para filtros
           document.addEventListener('DOMContentLoaded', function() {
               // Inicializar mapa
               initMap();
               
               // Cargar datos iniciales
               loadTrucksData();
               
               // Auto-refresh cada 30 segundos
               setInterval(loadTrucksData, 30000);
               
               // Event listeners para botones de filtro
               document.querySelectorAll('.btn-filter').forEach(button => {
                   button.addEventListener('click', function() {
                       const filterType = this.getAttribute('data-filter');
                       
                       // Determinar tipo de filtro
                       let filterCategory;
                       if (['all-alerts', 'critical', 'warning', 'attention', 'normal'].includes(filterType)) {
                           filterCategory = 'alert';
                           // Remover active de otros botones de alerta
                           document.querySelectorAll('[data-filter^="all-alerts"], [data-filter="critical"], [data-filter="warning"], [data-filter="attention"], [data-filter="normal"]').forEach(btn => {
                               btn.classList.remove('active');
                           });
                       } else if (['all-geo', 'docks', 'track-trace', 'cbn', 'ciudades'].includes(filterType)) {
                           filterCategory = 'geocerca';
                           // Remover active de otros botones de geocerca
                           document.querySelectorAll('[data-filter^="all-geo"], [data-filter="docks"], [data-filter="track-trace"], [data-filter="cbn"], [data-filter="ciudades"]').forEach(btn => {
                               btn.classList.remove('active');
                           });
                       } else if (['all-delivery', 'en-transito', 'en-ciudad', 'descargando'].includes(filterType)) {
                           filterCategory = 'delivery';
                           // Remover active de otros botones de delivery
                           document.querySelectorAll('[data-filter^="all-delivery"], [data-filter="en-transito"], [data-filter="en-ciudad"], [data-filter="descargando"]').forEach(btn => {
                               btn.classList.remove('active');
                           });
                       }
                       
                       // Activar botón actual
                       this.classList.add('active');
                       
                       // Actualizar filtros activos
                       activeFilters[filterCategory] = filterType;
                       
                       // Aplicar filtros
                       applyFilters();
                       updateTruckList();
                   });
               });
               
               // Keyboard shortcuts
               document.addEventListener('keydown', function(e) {
                   if (e.key === 'r' || e.key === 'R') {
                       if (e.ctrlKey || e.metaKey) {
                           e.preventDefault();
                           refreshData();
                       }
                   }
                   if (e.key === 'f' || e.key === 'F') {
                       if (e.ctrlKey || e.metaKey) {
                           e.preventDefault();
                           toggleFullscreen();
                       }
                   }
                   if (e.key === 'c' || e.key === 'C') {
                       if (e.ctrlKey || e.metaKey) {
                           e.preventDefault();
                           centerMapBolivia();
                       }
                   }
               });
           });
       </script>
   </body>
   </html>
   '''

@app.route('/api/map/trucks-geojson')
def get_trucks_geojson():
   """Endpoint que devuelve camiones en formato GeoJSON para mapas avanzados"""
   try:
       if not tracking_service_complete:
           init_complete_service()

       trucks = tracking_service_complete.get_all_trucks_status_complete()

       features = []
       for truck in trucks:
           if truck.get('latitude') and truck.get('longitude'):
               feature = {
                   "type": "Feature",
                   "geometry": {
                       "type": "Point",
                       "coordinates": [truck['longitude'], truck['latitude']]
                   },
                   "properties": {
                       "patente": truck['patente'],
                       "planilla": truck.get('planilla', ''),
                       "status": truck.get('status', ''),
                       "deposito_destino": truck.get('deposito_destino', ''),
                       "alert_level": truck.get('alert_level', 'NORMAL'),
                       "porcentaje_entrega": truck.get('porcentaje_entrega', 0),
                       "estado_entrega": truck.get('estado_entrega', 'EN_TRANSITO'),
                       "tiempo_espera_horas": truck.get('tiempo_espera_horas', 0),
                       "velocidad_kmh": truck.get('velocidad_kmh', 0),
                       "en_docks": truck.get('en_docks', 'NO'),
                       "en_track_trace": truck.get('en_track_trace', 'NO'),
                       "en_cbn": truck.get('en_cbn', 'NO'),
                       "en_ciudades": truck.get('en_ciudades', 'NO'),
                       "timestamp": truck.get('timestamp', ''),
                       "producto": truck.get('producto', '')
                   }
               }
               features.append(feature)

       geojson = {
           "type": "FeatureCollection",
           "features": features
       }

       return jsonify(geojson), 200

   except Exception as e:
       api.abort(500, f"Error generando GeoJSON: {str(e)}")

@app.route('/api/map/stats-summary')
def get_map_stats_summary():
   """Endpoint optimizado para estadísticas del mapa"""
   try:
       if not tracking_service_complete:
           init_complete_service()

       trucks = tracking_service_complete.get_all_trucks_status_complete()

       if not trucks:
           return jsonify({
               'total_trucks': 0,
               'by_alert_level': {},
               'by_geocerca': {},
               'by_estado': {},
               'avg_progress': 0,
               'timestamp': datetime.now().isoformat()
           })

       # Estadísticas por nivel de alerta
       by_alert = {}
       for truck in trucks:
           alert = truck.get('alert_level', 'NORMAL')
           by_alert[alert] = by_alert.get(alert, 0) + 1

       # Estadísticas por geocerca
       by_geocerca = {
           'docks': len([t for t in trucks if t.get('en_docks', 'NO') != 'NO']),
           'track_trace': len([t for t in trucks if t.get('en_track_trace', 'NO') != 'NO']),
           'cbn': len([t for t in trucks if t.get('en_cbn', 'NO') != 'NO']),
           'ciudades': len([t for t in trucks if t.get('en_ciudades', 'NO') != 'NO'])
       }

       # Estadísticas por estado de entrega
       by_estado = {}
       for truck in trucks:
           estado = truck.get('estado_entrega', 'EN_TRANSITO')
           by_estado[estado] = by_estado.get(estado, 0) + 1

       # Progreso promedio
       total_progress = sum(truck.get('porcentaje_entrega', 0) for truck in trucks)
       avg_progress = round(total_progress / len(trucks), 1) if trucks else 0

       return jsonify({
           'total_trucks': len(trucks),
           'by_alert_level': by_alert,
           'by_geocerca': by_geocerca,
           'by_estado': by_estado,
           'avg_progress': avg_progress,
           'in_geocercas': sum(by_geocerca.values()),
           'timestamp': datetime.now().isoformat()
       })

   except Exception as e:
       api.abort(500, f"Error generando estadísticas: {str(e)}")


# Inicializar al arrancar
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'

    print("Iniciando Sistema de Tracking CBN...")
    print(f"Puerto: {port}")
    print(f"Debug: {debug}")
    print(f"Base de datos: {app.config['DB_HOST']}")
    print(f"Entorno: {os.environ.get('FLASK_ENV', 'development')}")

    print("🚛 Iniciando Sistema de Tracking Completo...")
    print("🏠 Inicio: http://localhost:5000/")
    print("📊 Dashboard Completo: http://localhost:5000/dashboard")
    print("📖 Swagger API Completa: http://localhost:5000/docs/")
    print("🚨 Alertas: http://localhost:5000/api/alerts/active")
    print("📈 Excel Completo: http://localhost:5000/api/reports/excel-complete")

    # Inicializar servicio completo
    init_complete_service()

    app.run(host='0.0.0.0', port=5000, debug=True)