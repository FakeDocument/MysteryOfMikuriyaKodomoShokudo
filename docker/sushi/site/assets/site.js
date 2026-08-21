(() => {
  const button = document.querySelector('.nav-toggle');
  const navigation = document.querySelector('.global-nav');

  if (!button || !navigation) return;

  const closeMenu = () => {
    button.setAttribute('aria-expanded', 'false');
    button.querySelector('.sr-only').textContent = 'メニューを開く';
  };

  button.addEventListener('click', () => {
    const isOpen = button.getAttribute('aria-expanded') === 'true';
    button.setAttribute('aria-expanded', String(!isOpen));
    button.querySelector('.sr-only').textContent = isOpen ? 'メニューを開く' : 'メニューを閉じる';
  });

  navigation.addEventListener('click', (event) => {
    if (event.target instanceof HTMLAnchorElement) closeMenu();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      closeMenu();
      button.focus();
    }
  });
})();
