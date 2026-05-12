const socket = io(); 
socket.emit("join_class", {join_code: window.JOIN_CODE});

socket.on("chat_message", data => {
    addChatMessage(data.username, data.message);
});

socket.on("trade_update", data => {
    addSystemMessage(data.message);
});

function addChatMessage(username, message){
    const box = document.getElementById("chat-messages");

    const div = document.createElement("div");
    if(username === window.USERNAME){
        div.classList.add("chat-message", "me");
    } else {
        div.classList.add("chat-message", "them");
    }
    div.innerHTML = ` <strong> ${username} </strong>: ${message}`;

    box.appendChild(div);
    box.scrollTop = box.scrollHeight;


}

function addSystemMessage(message) {
    const box = document.getElementById("chat-messages");

    const div = document.createElement("div");
    div.classList.add("system-message");
    div.textContent = message;

    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
}

