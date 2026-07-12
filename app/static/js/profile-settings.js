const imageInput = document.querySelector("#profile_image");
if (imageInput) {
  imageInput.addEventListener("change", () => {
    const file = imageInput.files[0];
    if (!file) return;
    const preview = document.querySelector("#profile-preview");
    const fallback = document.querySelector("#profile-fallback");
    preview.src = URL.createObjectURL(file);
    preview.classList.remove("is-hidden");
    fallback?.classList.add("is-hidden");
  });
}

const dialog = document.querySelector("#delete-dialog");
document.querySelector("[data-open-delete]")?.addEventListener("click", () => dialog?.showModal());
document.querySelector("[data-close-delete]")?.addEventListener("click", () => dialog?.close());
document.querySelector("[data-confirm-delete]")?.addEventListener("click", () => {
  const form = document.createElement("form");
  form.method = "post";
  form.action = "/auth/settings/delete-conversations";
  const token = document.createElement("input");
  token.type = "hidden";
  token.name = "csrf_token";
  token.value = document.querySelector('meta[name="csrf-token"]').content;
  form.append(token);
  document.body.append(form);
  form.submit();
});
