(function () {
    function showDuration(duration) {
        document.querySelectorAll(".slot-list").forEach(function (el) {
            el.hidden = true;
        });
        document.querySelectorAll(".duration-tab").forEach(function (el) {
            el.classList.remove("active");
        });

        var slotList = document.getElementById("slots-" + duration);
        var activeTab = null;
        document.querySelectorAll(".duration-tab").forEach(function (el) {
            if (el.dataset.duration === duration) {
                activeTab = el;
            }
        });
        if (!slotList || !activeTab) {
            return;
        }

        slotList.hidden = false;
        activeTab.classList.add("active");
    }

    function insertForm(button) {
        document.querySelectorAll(".booking-form").forEach(function (el) {
            el.remove();
        });
        document.querySelectorAll(".slot-button").forEach(function (el) {
            el.classList.remove("contrast");
            el.classList.add("outline");
        });

        var form = button.closest("form");
        var template = document.getElementById("booking-form-template");
        if (!form || !template) {
            return;
        }

        var clone = template.content.cloneNode(true);
        var nameInput = clone.querySelector("#bf-name");
        var emailInput = clone.querySelector("#bf-email");
        nameInput.removeAttribute("id");
        emailInput.removeAttribute("id");
        nameInput.setAttribute("name", "name");
        emailInput.setAttribute("name", "email");
        form.appendChild(clone);

        button.classList.remove("outline");
        button.classList.add("contrast");
        form.querySelector('input[name="name"]').focus();
    }

    function toggleForm(button) {
        var form = button.closest("form");
        var bookingForm = form ? form.querySelector(".booking-form") : null;
        if (bookingForm) {
            bookingForm.remove();
            button.classList.remove("contrast");
            button.classList.add("outline");
            return;
        }
        insertForm(button);
    }

    document.addEventListener("click", function (event) {
        var durationTab = event.target.closest(".duration-tab");
        if (durationTab) {
            showDuration(durationTab.dataset.duration);
            return;
        }

        var slotButton = event.target.closest(".slot-button");
        if (slotButton) {
            toggleForm(slotButton);
        }
    });
})();
