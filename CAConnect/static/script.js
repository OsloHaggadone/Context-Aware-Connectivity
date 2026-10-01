const socket = io();

// Receive and display messages
socket.on('receive_message', function(data) {
    const messagesContainer = document.getElementById('chat-messages');
    const msgElement = document.createElement('div');
    msgElement.classList.add('message');
    msgElement.innerHTML = `<strong>${data.sender}:</strong> ${data.msg}`;
    
    messagesContainer.appendChild(msgElement);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
});

// Update background image and prompt caption
socket.on('update_background', function(data) {
    document.body.style.backgroundImage = `url('${data.url}')`;
    
    const captionElement = document.getElementById('prompt-caption');
    if (captionElement && data.prompt) {
        captionElement.innerText = data.prompt;
    }
});

// Send message to server with viewport dimensions
function sendMessage() {
    const input = document.getElementById('message-input');
    const messageText = input.value.trim();

    if (!messageText) return;

    socket.emit('send_message', {
        sender: "User",
        msg: messageText,
        width: Math.round(window.innerWidth * (window.devicePixelRatio || 1)),
        height: Math.round(window.innerHeight * (window.devicePixelRatio || 1))
    });

    input.value = '';
}