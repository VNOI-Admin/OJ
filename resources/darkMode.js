const sun = document.querySelector('.sun');
const moon = document.querySelector('.moon');
const themeToggler = document.querySelector('.toggle-theme');
const currentTheme = localStorage.getItem('theme') || 'light';

const changeIcon = (theme) => {
    if (theme === 'light') {
        sun.classList.remove('hidden');
        moon.classList.add('hidden');
    } else {
        moon.classList.remove('hidden');
        sun.classList.add('hidden');
    }
}
changeIcon(currentTheme);

themeToggler.addEventListener('click', (e) => {
    e.preventDefault();
    const currentTheme = localStorage.getItem('theme') || 'light';

    console.log(currentTheme);
    if (currentTheme === 'light') {
        document.body.classList.remove(currentTheme);
        const newTheme = 'dark';
        document.body.classList.add(newTheme);
        moon.classList.remove('hidden');
        sun.classList.add('hidden');
        localStorage.setItem('theme', newTheme);
    } else {
        document.body.classList.remove(currentTheme);
        const newTheme = 'light';
        document.body.classList.add(newTheme);
        localStorage.setItem('theme', newTheme);
        sun.classList.remove('hidden');
        moon.classList.add('hidden');
    }
})
