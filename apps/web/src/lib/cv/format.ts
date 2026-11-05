const formatter = new Intl.DateTimeFormat('fr-FR', {
	day: 'numeric',
	month: 'long',
	hour: '2-digit',
	minute: '2-digit',
	timeZone: undefined
});

/** "le 5 novembre à 18:42", for a sentence such as "enregistrée le 5 novembre à 18:42". */
export const savedOn = (date: string | null) =>
	date ? `le ${formatter.format(new Date(date))}` : '';
