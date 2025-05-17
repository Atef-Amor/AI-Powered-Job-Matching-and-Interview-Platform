// Animation for button click
document.querySelectorAll("button").forEach(button => {
    button.addEventListener("click", function() {
        this.classList.add("clicked");
        setTimeout(() => {
            this.classList.remove("clicked");
        }, 200);
    });
});

// Add class to change background color on hover (for buttons)
const buttons = document.querySelectorAll("button");

buttons.forEach(button => {
    button.addEventListener("mouseover", () => {
        button.style.backgroundColor = "#2980b9";
    });
    button.addEventListener("mouseout", () => {
        button.style.backgroundColor = "#3498db";
    });
});

// Smooth scroll to the top button (can be added to footer or page)
const scrollToTopButton = document.createElement("button");
scrollToTopButton.textContent = "Retour en haut";
scrollToTopButton.classList.add("btn", "btn-secondary", "scroll-to-top");
document.body.appendChild(scrollToTopButton);

scrollToTopButton.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
});

// Show/Hide loader animation (for example, when submitting a form)
function showLoader() {
    const loader = document.createElement("div");
    loader.classList.add("loader");
    document.body.appendChild(loader);
}

function hideLoader() {
    const loader = document.querySelector(".loader");
    if (loader) loader.remove();
}
