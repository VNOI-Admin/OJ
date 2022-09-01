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
};
changeIcon(currentTheme);

const changeTheme = (theme) => {
	if (!theme) theme = localStorage.getItem('theme') || 'light';

	if (theme === 'light') {
		document.body.classList.remove(theme);
		const newTheme = 'dark';
		document.body.classList.add(newTheme);
		localStorage.setItem('theme', newTheme);
		changeIcon(newTheme);
	} else {
		document.body.classList.remove(theme);
		const newTheme = 'light';
		document.body.classList.add(newTheme);
		localStorage.setItem('theme', newTheme);
		changeIcon(newTheme);
	}
};

themeToggler.addEventListener('click', (e) => {
	e.preventDefault();
	const currentTheme = localStorage.getItem('theme') || 'light';

	changeTheme(currentTheme);
});

function renderChart(chart) {
	const theme = localStorage.getItem('theme') || 'light';
	const newTheme = theme === 'light' ? 'dark' : 'light';
	chart.options.legend.labels.fontColor = `${
		newTheme === 'light' ? 'black' : 'white'
	}`;
	chart.render();
}
