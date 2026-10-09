"use strict";

document.querySelectorAll(".password-toggle").forEach((button) => {
    button.addEventListener("click", () => {
        const input = document.getElementById(button.getAttribute("aria-controls"));

        if (!input) {
            return;
        }

        const willShow = input.type === "password";
        input.type = willShow ? "text" : "password";
        button.textContent = willShow ? "Hide" : "Show";
        button.setAttribute("aria-pressed", String(willShow));

        const fieldName = input.name === "confirm_password"
            ? "password confirmation"
            : "password";
        button.setAttribute(
            "aria-label",
            `${willShow ? "Hide" : "Show"} ${fieldName}`,
        );
    });
});
