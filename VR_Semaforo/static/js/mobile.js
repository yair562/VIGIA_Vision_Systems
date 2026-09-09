const video = document.getElementById("video");
const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");
const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const verDeteccion = document.getElementById("verDeteccion");
const imagenAnotada = document.getElementById("imagenAnotada");

// Nuevos elementos del panel de decisión (Agente Local)
const resCarritos = document.getElementById("res_carritos");
const resEstado = document.getElementById("res_estado");
const resVerde = document.getElementById("res_verde");

// Obtenemos la URL inyectada en el HTML
const serverUrl = window.SERVER_URL || ""; 
let captureInterval = null;
let isProcessing = false;

// 1. Iniciar cámara trasera
async function startCamera() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: "environment" }
        });
        video.srcObject = stream;
        await video.play();
    } catch (err) {
        console.error("❌ Error cámara: ", err.message);
        resCarritos.innerText = "Error";
        resEstado.innerText = "Sin Cámara";
    }
}

// 2. Enviar un frame al servidor y actualizar el panel
async function sendFrame() {
    if (isProcessing) return;
    if (!video.videoWidth || !video.videoHeight) return;

    isProcessing = true;
    const ver = verDeteccion.checked;

    try {
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

        // Generar la imagen (mayor calidad si se va a dibujar encima)
        const blob = await new Promise(resolve =>
            canvas.toBlob(resolve, "image/jpeg", ver ? 0.9 : 0.7)
        );

        const formData = new FormData();
        formData.append("image", blob, "live.jpg");
        formData.append("dibujar", ver ? "true" : "false");

        // Mandamos el frame al backend de Flask
        const response = await fetch(serverUrl + "/capture-mobile", {
            method: "POST",
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            // Alimentar el nuevo panel con las decisiones del backend
            resCarritos.innerText = data.carritos;
            resEstado.innerText = data.estado;
            resVerde.innerText = data.verde;
            
            // Lógica para mostrar los recuadros de YOLO
            if (ver && data.imagen_anotada) {
                imagenAnotada.src = data.imagen_anotada;
                imagenAnotada.style.display = "block";
                video.style.display = "none"; // Ocultar el video crudo para evitar empalmes
            } else {
                imagenAnotada.style.display = "none";
                video.style.display = "block"; // Regresar al video en vivo
            }
        } else {
            console.error("Error en la detección de la imagen.");
        }
    } catch (err) {
        console.error("Error de conexión con el servidor: ", err.message);
    } finally {
        isProcessing = false;
    }
}

// 3. Control de intervalo (Loop del Agente)
function startLiveDetection() {
    if (captureInterval) return;
    captureInterval = setInterval(sendFrame, 400); // Se envía foto cada 400ms
    startBtn.style.display = "none";
    stopBtn.style.display = "inline-block";
}

function stopLiveDetection() {
    clearInterval(captureInterval);
    captureInterval = null;
    startBtn.style.display = "inline-block";
    stopBtn.style.display = "none";
    
    // Limpiar métricas de la pantalla
    resCarritos.innerText = "--";
    resEstado.innerText = "--";
    resVerde.innerText = "--";
    
    imagenAnotada.style.display = "none";
    video.style.display = "block";
}

// 4. Asociar eventos a los botones
startBtn.addEventListener("click", startLiveDetection);
stopBtn.addEventListener("click", stopLiveDetection);

// Restaurar la vista si se apaga el checkbox en pleno vuelo
verDeteccion.addEventListener('change', () => {
    if (!verDeteccion.checked) {
        imagenAnotada.style.display = 'none';
        video.style.display = 'block';
    }
});

// 5. Al cargar el script, encender la cámara
startCamera();