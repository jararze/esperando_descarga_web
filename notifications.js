// notifications.js - Sistema de notificaciones push
class AlertNotificationSystem {
    constructor() {
        this.permission = 'default';
        this.lastAlertCount = 0;
        this.init();
    }

    async init() {
        // Solicitar permisos de notificación
        if ('Notification' in window) {
            this.permission = await Notification.requestPermission();
        }

        // Verificar alertas cada minuto
        setInterval(() => {
            this.checkForNewAlerts();
        }, 60000);
    }

    async checkForNewAlerts() {
        try {
            const response = await fetch('/api/alerts/summary');
            const data = await response.json();
            const currentCount = data.critical_count + data.warning_count;

            if (currentCount > this.lastAlertCount) {
                const newAlerts = currentCount - this.lastAlertCount;
                this.showNotification('Nuevas Alertas',
                    `${newAlerts} nuevas alertas detectadas`, 'warning');
            }

            this.lastAlertCount = currentCount;
        } catch (error) {
            console.error('Error verificando alertas:', error);
        }
    }

    showNotification(title, message, type = 'info') {
        if (this.permission === 'granted') {
            const notification = new Notification(title, {
                body: message,
                icon: '/static/icons/alert-icon.png',
                badge: '/static/icons/badge-icon.png',
                tag: 'cbn-alerts',
                requireInteraction: type === 'critical'
            });

            notification.onclick = () => {
                window.focus();
                window.open('/alerts-dashboard', '_blank');
                notification.close();
            };

            // Auto-cerrar después de 5 segundos (excepto críticas)
            if (type !== 'critical') {
                setTimeout(() => notification.close(), 5000);
            }
        }
    }

    // Simular envío de notificación WhatsApp
    async sendWhatsAppNotification(alertData) {
        const message = `🚨 ALERTA CBN
Camión: ${alertData.patente}
Destino: ${alertData.deposito_destino}
Tiempo espera: ${alertData.tiempo_espera_horas}h
Estado: ${alertData.alert_level}`;

        // En producción, aquí iría la integración con WhatsApp API
        console.log('WhatsApp message:', message);
        return true;
    }

    // Simular envío de email
    async sendEmailNotification(alertData) {
        const emailData = {
            to: 'operaciones@cbn.com',
            subject: `Alerta ${alertData.alert_level} - Camión ${alertData.patente}`,
            body: this.generateEmailBody(alertData)
        };

        // En producción, aquí iría la integración con servicio de email
        console.log('Email notification:', emailData);
        return true;
    }

    generateEmailBody(alertData) {
        return `
        <h2>Alerta de Tracking CBN</h2>
        <p><strong>Nivel:</strong> ${alertData.alert_level}</p>
        <p><strong>Camión:</strong> ${alertData.patente}</p>
        <p><strong>Planilla:</strong> ${alertData.planilla}</p>
        <p><strong>Destino:</strong> ${alertData.deposito_destino}</p>
        <p><strong>Tiempo de espera:</strong> ${alertData.tiempo_espera_horas} horas</p>
        <p><strong>Estado:</strong> ${alertData.estado_entrega}</p>
        <p><strong>Generado:</strong> ${new Date().toLocaleString()}</p>
        
        <p><a href="http://localhost:5000/alerts-dashboard">Ver Dashboard de Alertas</a></p>
        `;
    }
}

// Inicializar sistema de notificaciones
const notificationSystem = new AlertNotificationSystem();