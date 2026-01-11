// app/static/js/app.js
const { createApp, ref, computed, onMounted } = Vue;

const app = createApp({
    setup() {
        const input = ref("");
        const serverRecipe = ref("");
        const liveRecipe = ref("");
        const loading = ref(false);
        const error = ref("");
        const sessionId = ref(Math.random().toString(36).slice(2, 8).toUpperCase());
        
        // Аутентификация
        const user = ref(null);
        const csrfToken = ref(null);
        const showLoginModal = ref(false);
        const showRegisterModal = ref(false);
        const loginUsername = ref("");
        const loginPassword = ref("");
        const registerUsername = ref("");
        const registerPassword = ref("");
        const authError = ref("");
        const authLoading = ref(false);
        
        // Рецепты
        const savedRecipes = ref([]);
        const currentRecipeId = ref(null);
        const isEditing = ref(false);
        const editedContent = ref("");
        const recipeTitle = ref("");
        const showCatalog = ref(false);
        const savingRecipe = ref(false);
        const activeTab = ref("generate"); // "generate" | "cabinet"

        const currentRecipe = computed(() => {
            return liveRecipe.value || serverRecipe.value || "";
        });

        const shortGameHint = computed(() => {
            if (!input.value) return "Укажите игру, блюдо и желаемый стиль подачи.";
            const lower = input.value.toLowerCase();
            if (lower.includes("witcher") || lower.includes("ведьмак")) return "Подходит для тёмного фэнтези и северной кухни.";
            if (lower.includes("stardew")) return "Идеально для уютных посиделок или пикника.";
            if (lower.includes("skyrim")) return "Позаботьтесь о сытности и тёплых специях.";
            return "Добавьте детали про игру, настроение и ограничения по ингредиентам.";
        });

        const sessionLabel = computed(() => {
            return `${sessionId.value}`;
        });

        // Функция для очистки HTML тегов из текста
        const cleanHtmlTags = (text) => {
            if (!text) return "";
            // Заменяем <br>, <br/>, <br /> на переводы строк
            text = text.replace(/<br\s*\/?>/gi, '\n');
            // Удаляем другие HTML теги
            text = text.replace(/<[^>]+>/g, '');
            // Декодируем HTML entities
            text = text.replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>');
            return text;
        };

        // Загрузка рецептов
        const loadRecipes = async () => {
            if (!user.value) return;
            try {
                const response = await fetch("/api/recipes");
                const data = await response.json();
                // Очищаем HTML теги из всех сохранённых рецептов
                savedRecipes.value = (data.recipes || []).map(recipe => ({
                    ...recipe,
                    content: cleanHtmlTags(recipe.content)
                }));
            } catch (e) {
                console.error("Ошибка загрузки рецептов:", e);
            }
        };

        // Получение CSRF токена из cookie
        const getCsrfTokenFromCookie = () => {
            const cookies = document.cookie.split(';');
            for (let cookie of cookies) {
                const [name, value] = cookie.trim().split('=');
                if (name === 'csrf_token') {
                    return value;
                }
            }
            return null;
        };

        // Обновление CSRF токена
        const updateCsrfToken = (token) => {
            csrfToken.value = token;
        };

        // Получение CSRF токена с сервера
        const fetchCsrfToken = async () => {
            try {
                const response = await fetch("/api/auth/csrf-token");
                const data = await response.json();
                if (data.csrf_token) {
                    updateCsrfToken(data.csrf_token);
                }
            } catch (e) {
                console.error("Ошибка получения CSRF токена:", e);
            }
        };

        // Обёртка для fetch с автоматическим добавлением CSRF токена
        const fetchWithCsrf = async (url, options = {}) => {
            // Обновляем CSRF токен из cookie перед каждым запросом
            const tokenFromCookie = getCsrfTokenFromCookie();
            if (tokenFromCookie) {
                updateCsrfToken(tokenFromCookie);
            }

            // Добавляем CSRF токен в заголовки для изменяющих методов
            const method = (options.method || 'GET').toUpperCase();
            if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
                const headers = options.headers || {};
                if (csrfToken.value) {
                    headers['X-CSRF-Token'] = csrfToken.value;
                }
                options.headers = headers;
            }

            const response = await fetch(url, options);
            
            // Если получили 403, возможно CSRF токен устарел - обновляем
            if (response.status === 403) {
                await fetchCsrfToken();
                // Повторяем запрос с новым токеном
                if (csrfToken.value && ['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
                    const headers = options.headers || {};
                    headers['X-CSRF-Token'] = csrfToken.value;
                    options.headers = headers;
                    return await fetch(url, options);
                }
            }
            
            return response;
        };

        // Проверка авторизации при загрузке
        const checkAuth = async () => {
            try {
                const response = await fetch("/api/auth/me");
                const data = await response.json();
                if (data.user) {
                    user.value = data.user;
                    if (data.csrf_token) {
                        updateCsrfToken(data.csrf_token);
                    } else {
                        await fetchCsrfToken();
                    }
                    await loadRecipes();
                } else {
                    // Пытаемся получить CSRF токен из cookie
                    const tokenFromCookie = getCsrfTokenFromCookie();
                    if (tokenFromCookie) {
                        updateCsrfToken(tokenFromCookie);
                    }
                }
            } catch (e) {
                console.error("Ошибка проверки авторизации:", e);
            }
        };

        // Регистрация
        const handleRegister = async () => {
            authError.value = "";
            authLoading.value = true;
            try {
                const response = await fetch("/api/auth/register", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        username: registerUsername.value,
                        password: registerPassword.value
                    })
                });
                
                if (!response.ok) {
                    const data = await response.json();
                    throw new Error(data.detail || "Ошибка регистрации");
                }
                
                const data = await response.json();
                user.value = { username: data.username };
                if (data.csrf_token) {
                    updateCsrfToken(data.csrf_token);
                }
                showRegisterModal.value = false;
                registerUsername.value = "";
                registerPassword.value = "";
                await loadRecipes();
            } catch (e) {
                authError.value = e.message;
            } finally {
                authLoading.value = false;
            }
        };

        // Вход
        const handleLogin = async () => {
            authError.value = "";
            authLoading.value = true;
            try {
                const response = await fetch("/api/auth/login", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        username: loginUsername.value,
                        password: loginPassword.value
                    })
                });
                
                if (!response.ok) {
                    const data = await response.json();
                    throw new Error(data.detail || "Неверное имя пользователя или пароль");
                }
                
                const data = await response.json();
                user.value = { username: data.username };
                if (data.csrf_token) {
                    updateCsrfToken(data.csrf_token);
                }
                showLoginModal.value = false;
                loginUsername.value = "";
                loginPassword.value = "";
                await loadRecipes();
            } catch (e) {
                authError.value = e.message;
            } finally {
                authLoading.value = false;
            }
        };

        // Выход
        const handleLogout = async () => {
            try {
                await fetchWithCsrf("/api/auth/logout", { method: "POST" });
                user.value = null;
                csrfToken.value = null;
                savedRecipes.value = [];
                currentRecipeId.value = null;
                isEditing.value = false;
            } catch (e) {
                console.error("Ошибка выхода:", e);
            }
        };

        // Сохранение рецепта
        const saveRecipe = async () => {
            if (!user.value || !currentRecipe.value) return;
            
            savingRecipe.value = true;
            try {
                // Извлекаем заголовок из рецепта (первая строка или первые 50 символов)
                const content = currentRecipe.value;
                const lines = content.split("\n").filter(l => l.trim());
                const title = recipeTitle.value || lines[0]?.substring(0, 50) || "Рецепт без названия";
                
                const response = await fetchWithCsrf("/api/recipes", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        title: title,
                        content: currentRecipe.value,
                        original_query: input.value
                    })
                });
                
                if (!response.ok) {
                    throw new Error("Ошибка сохранения рецепта");
                }
                
                await loadRecipes();
                recipeTitle.value = "";
                alert("Рецепт сохранён!");
            } catch (e) {
                alert("Ошибка сохранения: " + e.message);
            } finally {
                savingRecipe.value = false;
            }
        };

        // Загрузка рецепта для редактирования
        const loadRecipeForEdit = async (recipeId) => {
            try {
                const response = await fetch(`/api/recipes/${recipeId}`);
                const data = await response.json();
                // Очищаем HTML теги из сохранённого рецепта
                const cleanContent = cleanHtmlTags(data.content);
                liveRecipe.value = cleanContent;
                recipeTitle.value = data.title;
                currentRecipeId.value = recipeId;
                isEditing.value = true;
                editedContent.value = cleanContent;
                showCatalog.value = false;
            } catch (e) {
                alert("Ошибка загрузки рецепта: " + e.message);
            }
        };

        // Сохранение изменений
        const saveEdit = async () => {
            if (!currentRecipeId.value) return;
            
            savingRecipe.value = true;
            try {
                const response = await fetchWithCsrf(`/api/recipes/${currentRecipeId.value}`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        title: recipeTitle.value,
                        content: editedContent.value
                    })
                });
                
                if (!response.ok) {
                    throw new Error("Ошибка сохранения изменений");
                }
                
                liveRecipe.value = editedContent.value;
                isEditing.value = false;
                await loadRecipes();
                alert("Изменения сохранены!");
            } catch (e) {
                alert("Ошибка сохранения: " + e.message);
            } finally {
                savingRecipe.value = false;
            }
        };

        // Отмена редактирования
        const cancelEdit = () => {
            isEditing.value = false;
            editedContent.value = "";
            currentRecipeId.value = null;
            recipeTitle.value = "";
        };

        // Удаление рецепта
        const deleteRecipe = async (recipeId) => {
            if (!confirm("Удалить этот рецепт?")) return;
            
            try {
                const response = await fetchWithCsrf(`/api/recipes/${recipeId}`, {
                    method: "DELETE"
                });
                
                if (!response.ok) {
                    throw new Error("Ошибка удаления");
                }
                
                await loadRecipes();
                if (currentRecipeId.value === recipeId) {
                    cancelEdit();
                    liveRecipe.value = "";
                }
            } catch (e) {
                alert("Ошибка удаления: " + e.message);
            }
        };

        const applyExample = (text) => {
            if (loading.value) return;
            input.value = text;
        };

        const handleSubmit = async () => {
            if (!input.value.trim() || loading.value) return;
            loading.value = true;
            error.value = "";

            try {
                const response = await fetch("/api/recipe", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    body: JSON.stringify({ chat_input: input.value.trim() }),
                });

                if (!response.ok) {
                    throw new Error("Сервис временно недоступен. Попробуйте ещё раз позже.");
                }

                const data = await response.json();
                // Очищаем HTML теги из рецепта
                liveRecipe.value = cleanHtmlTags(data.recipe || "");
                serverRecipe.value = "";
                // Сбрасываем редактирование при новом рецепте
                isEditing.value = false;
                currentRecipeId.value = null;
                recipeTitle.value = "";
            } catch (e) {
                console.error(e);
                error.value = e.message || "Произошла ошибка при получении рецепта.";
            } finally {
                loading.value = false;
            }
        };

        onMounted(() => {
            // Очищаем рецепты при загрузке
            serverRecipe.value = "";
            liveRecipe.value = "";
            
            // Проверяем авторизацию через API
            checkAuth();
        });

        return {
            input,
            loading,
            error,
            currentRecipe,
            shortGameHint,
            sessionLabel,
            applyExample,
            handleSubmit,
            user,
            showLoginModal,
            showRegisterModal,
            loginUsername,
            loginPassword,
            registerUsername,
            registerPassword,
            authError,
            authLoading,
            handleRegister,
            handleLogin,
            handleLogout,
            savedRecipes,
            currentRecipeId,
            isEditing,
            editedContent,
            recipeTitle,
            showCatalog,
            savingRecipe,
            activeTab,
            saveRecipe,
            loadRecipeForEdit,
            saveEdit,
            cancelEdit,
            deleteRecipe,
            loadRecipes
        };
    },
});

app.config.compilerOptions.delimiters = ["[[", "]]"];

// Проверяем, что элемент существует перед монтированием
if (document.getElementById("app")) {
    app.mount("#app");
} else {
    console.error("Элемент #app не найден!");
}

