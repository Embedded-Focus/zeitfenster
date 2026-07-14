(function () {
    var capConstructorPromise = null;

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

    function clearCustomValidity(form) {
        form.querySelectorAll("input, button").forEach(function (field) {
            if (typeof field.setCustomValidity === "function") {
                field.setCustomValidity("");
            }
        });
    }

    function validationTargetForMessage(form, message) {
        if (message.indexOf("name") === 0) {
            return form.querySelector('input[name="name"]');
        }
        if (message.indexOf("email") === 0 || message === "Invalid email") {
            return form.querySelector('input[name="email"]');
        }
        return form.querySelector('.booking-form button[type="submit"]');
    }

    function showValidationMessage(form, message) {
        var target = validationTargetForMessage(form, message);
        if (!target || typeof target.setCustomValidity !== "function") {
            return;
        }
        target.setCustomValidity(message);
        target.reportValidity();
    }

    function readErrorMessage(response) {
        return response
            .json()
            .then(function (data) {
                if (data && typeof data.detail === "string") {
                    return data.detail;
                }
                return "The booking could not be submitted.";
            })
            .catch(function () {
                return "The booking could not be submitted.";
            });
    }

    function capConfig() {
        var root = document.querySelector("[data-cap-api-endpoint]");
        if (!root) {
            return null;
        }
        return {
            apiEndpoint: root.dataset.capApiEndpoint,
            widgetScriptUrl: root.dataset.capWidgetScriptUrl,
            wasmUrl: root.dataset.capWasmUrl
        };
    }

    function loadScript(src) {
        return new Promise(function (resolve, reject) {
            var existing = null;
            Array.prototype.forEach.call(document.scripts, function (script) {
                if (script.getAttribute("src") === src) {
                    existing = script;
                }
            });
            if (existing) {
                if (existing.dataset.loaded === "true") {
                    resolve();
                    return;
                }
                existing.addEventListener("load", resolve, { once: true });
                existing.addEventListener("error", reject, { once: true });
                return;
            }

            var script = document.createElement("script");
            script.src = src;
            script.async = true;
            script.addEventListener(
                "load",
                function () {
                    script.dataset.loaded = "true";
                    resolve();
                },
                { once: true }
            );
            script.addEventListener("error", reject, { once: true });
            document.head.appendChild(script);
        });
    }

    function loadCapConstructor(scriptUrl) {
        if (window.Cap) {
            return Promise.resolve(window.Cap);
        }
        if (!capConstructorPromise) {
            capConstructorPromise = import(scriptUrl)
                .then(function (module) {
                    return module.default || module.Cap || window.Cap;
                })
                .catch(function () {
                    return loadScript(scriptUrl).then(function () {
                        return window.Cap;
                    });
                })
                .then(function (Cap) {
                    if (!Cap) {
                        throw new Error("CAPTCHA could not be loaded.");
                    }
                    return Cap;
                });
        }
        return capConstructorPromise;
    }

    function solveCaptchaIfConfigured(formData) {
        var config = capConfig();
        if (!config) {
            return Promise.resolve(formData);
        }
        if (!config.apiEndpoint || !config.widgetScriptUrl || !config.wasmUrl) {
            return Promise.reject(new Error("CAPTCHA is not configured."));
        }
        window.CAP_CUSTOM_WASM_URL = config.wasmUrl;
        return loadCapConstructor(config.widgetScriptUrl)
            .then(function (Cap) {
                var cap = new Cap({
                    apiEndpoint: config.apiEndpoint
                });
                return cap.solve();
            })
            .then(function (solution) {
                if (!solution || !solution.token) {
                    throw new Error("CAPTCHA verification failed.");
                }
                formData.set("cap-token", solution.token);
                return formData;
            });
    }

    function submitBooking(form) {
        var submitButton = form.querySelector('.booking-form button[type="submit"]');
        clearCustomValidity(form);

        if (!form.reportValidity()) {
            return;
        }

        if (submitButton) {
            submitButton.disabled = true;
            submitButton.setAttribute("aria-busy", "true");
        }

        solveCaptchaIfConfigured(new FormData(form))
            .then(function (formData) {
                return fetch(form.action, {
                    method: "POST",
                    body: formData,
                    headers: {
                        Accept: "text/html, application/json"
                    }
                });
            })
            .then(function (response) {
                if (!response.ok) {
                    return readErrorMessage(response).then(function (message) {
                        throw new Error(message);
                    });
                }
                return response.text();
            })
            .then(function (html) {
                document.open();
                document.write(html);
                document.close();
            })
            .catch(function (error) {
                showValidationMessage(
                    form,
                    error.message || "The booking could not be submitted."
                );
            })
            .finally(function () {
                if (submitButton) {
                    submitButton.disabled = false;
                    submitButton.removeAttribute("aria-busy");
                }
            });
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

    document.addEventListener("submit", function (event) {
        var form = event.target.closest("form");
        if (!form || !form.querySelector(".booking-form")) {
            return;
        }
        event.preventDefault();
        submitBooking(form);
    });

    document.addEventListener("input", function (event) {
        if (typeof event.target.setCustomValidity === "function") {
            event.target.setCustomValidity("");
        }
    });
})();
